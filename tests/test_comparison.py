"""What the multi-run comparison must refuse to do.

A comparison is easy to make and easy to make dishonest: the failures defended
here are pairing across worlds, blanks that read as zeros, and a delta quoted
without the parameter that caused it.
"""

from __future__ import annotations

import ast
import csv
import json
import re
from pathlib import Path

import pytest

from harness.engine.analysis import Report
from harness.engine.comparison import (MANIFEST_IGNORED, NOT_RECORDED,
                                       PARAMETERS, Comparison, ComparisonError,
                                       Mixed, RunRef, extract, label_runs)
from harness.engine.comparison_csv import write as write_csv
from harness.engine.comparison_html import render_html, standalone_html
from harness.engine.comparison_text import render as render_text
from harness.engine.glossary import lookup
from harness.engine.results import LEDGER, ResultStore

BASE = dict(
    run_id="r1", arm="A1", task_id="t1", core_id="c1", task_class="R",
    answerable=True, repeat=0, outcome="pass", detail="", confident=False,
    clobbered=[], turns=3, calls=2, forbidden_attempts=0, truncated=False,
    error=None, wall_clock_seconds=1.0, input_tokens=1000,
    cached_input_tokens=0, output_tokens=100, reasoning_tokens=0,
    static_tokens=500, per_call_overhead_tokens=0, session_setup_tokens=0,
    model="gpt-5.6-luna", mcp_spec_revision="2026-07-28",
    skill_condition="none", report_class="controlled", seed=1, surface_size=0,
    metrics={"turns": 3},
)

_WORLD = dict(seed=1, cores=4, fan_out=8, difficulty="standard")


def row(**over):
    return {**BASE, **over}


def rows_for(arm: str, *, passes: int, fails: int = 0, core: str = "c1",
             **over) -> list[dict]:
    out = [row(arm=arm, outcome="pass", core_id=core, task_id=f"{core}-p{i}",
               **over) for i in range(passes)]
    out += [row(arm=arm, outcome="fail", core_id=core, task_id=f"{core}-f{i}",
                **over) for i in range(fails)]
    return out


def _run(label: str, rows: list[dict], path: str | None = None,
         mde_pp: float | None = None, **manifest) -> RunRef:
    return RunRef(
        label=label,
        path=path or f"/tmp/{label}",
        report=Report(rows=rows,
                      manifest={"id": label, "model": "gpt-5.6-luna", **manifest},
                      mde_pp=mde_pp),
    )


def _cmp(*runs: RunRef) -> Comparison:
    return Comparison(runs=list(runs))


# ---- arm intersection ----------------------------------------------------

def test_only_arms_every_run_has_are_compared() -> None:
    """A subset arm must not enter the head-to-head."""
    a = _run("a", rows_for("A1", passes=2) + rows_for("B1", passes=2)
             + rows_for("Z0", passes=1, mcp_spec_revision=None))
    b = _run("b", rows_for("A1", passes=2) + rows_for("C1", passes=2)
             + rows_for("Z0", passes=1, mcp_spec_revision=None))
    c = _cmp(a, b)
    assert c.shared_arms == ["A1", "Z0"]
    assert "B1" in c.exclusive_arms and c.exclusive_arms["B1"] == ["a"]
    assert "C1" in c.exclusive_arms and c.exclusive_arms["C1"] == ["b"]


def test_no_shared_arms_says_so_instead_of_an_empty_table() -> None:
    """The full-vs-missing-arms shape must not render a blank head-to-head."""
    a = _run("a", rows_for("A1", passes=2))
    b = _run("b", rows_for("B1", passes=2))
    c = _cmp(a, b)
    assert c.shared_arms == []
    text = render_text(c)
    html = render_html(c)
    assert "nothing to compare head to head" in text
    assert "No arm is present in every run" in html


def test_no_delta_cell_is_ever_blank() -> None:
    """A blank reads as a zero — the exact lie exclusive arms would create."""
    a = _run("a", rows_for("A1", passes=2) + rows_for("B1", passes=1))
    b = _run("b", rows_for("A1", passes=1, fails=1))
    c = _cmp(a, b)
    text = render_text(c)
    html = render_html(c)
    # Shared-arm deltas format through fmt_delta; None becomes "n/a".
    for arm in c.shared_arms:
        delta = c.delta("b", arm, "success")
        rendered = Comparison.fmt_delta("success", delta)
        assert rendered != ""
        assert rendered in text and rendered in html


def test_a_missing_value_makes_the_delta_absent_not_zero() -> None:
    """An absent number is not an equal one.

    A shared arm can still have no value on a dimension — here every run of it
    was truncated, so there is no graded success rate to subtract. Returning
    0.0 would render as `+0 pp`, which claims the two runs measured the same
    thing and found no difference. They measured nothing.
    """
    a = _run("a", rows_for("A1", passes=2))
    b = _run("b", [row(arm="A1", outcome="truncated", truncated=True)])
    c = _cmp(a, b)

    assert "A1" in c.shared_arms
    assert c.value("b", "A1", "success") is None
    assert c.delta("b", "A1", "success") is None, "an absent value became a zero"
    rendered = Comparison.fmt_delta("success", c.delta("b", "A1", "success"))
    assert rendered == "n/a"
    assert rendered in render_text(c) and rendered in render_html(c)


# ---- parameter diff ------------------------------------------------------

def test_a_differing_parameter_is_named_with_every_runs_value() -> None:
    a = _run("a", rows_for("A1", passes=1), difficulty="standard")
    b = _run("b", rows_for("A1", passes=1), difficulty="hard")
    c = _cmp(a, b)
    names = {p.name for p in c.differing}
    assert "difficulty" in names
    row = next(p for p in c.differing if p.name == "difficulty")
    assert row.values["a"] == "standard" and row.values["b"] == "hard"


def test_not_recorded_is_uncertain_not_differs() -> None:
    """Missing on one side is uncertainty, not disagreement."""
    a = _run("a", rows_for("A1", passes=1), temperature=0.0)
    b = _run("b", rows_for("A1", passes=1))  # no temperature
    c = _cmp(a, b)
    temp = next(p for p in c.params if p.name == "temperature")
    assert temp.uncertain
    assert not temp.differs


def test_both_runs_missing_a_parameter_is_not_a_difference() -> None:
    a = _run("a", rows_for("A1", passes=1))
    b = _run("b", rows_for("A1", passes=1))
    c = _cmp(a, b)
    temp = next(p for p in c.params if p.name == "temperature")
    assert temp.values["a"] is NOT_RECORDED
    assert temp.values["b"] is NOT_RECORDED
    assert not temp.differs
    assert not temp.uncertain


def test_axes_fill_in_what_the_manifest_omits() -> None:
    rows = rows_for("A1", passes=1,
                    axes={"schema_detail": "terse", "name": "MCP, all tools"})
    a = _run("a", rows)
    value, source = extract(a.report,
                            next(p for p in PARAMETERS if p.name == "schema detail"))
    assert value == "terse" and source == "axes"


def test_a_sweep_reads_as_mixed() -> None:
    rows = (rows_for("A1", passes=1, axes={"error_detail": "terse"})
            + rows_for("A1", passes=1, core="c2",
                       axes={"error_detail": "field-scoped"}))
    a = _run("a", rows)
    value, _ = extract(a.report,
                       next(p for p in PARAMETERS if p.name == "error detail"))
    assert isinstance(value, Mixed)
    assert set(value.values) == {"terse", "field-scoped"}


@pytest.mark.parametrize("absent", [None, "", "none"])
def test_null_mcp_revision_is_an_absence_not_a_revision(absent) -> None:
    """A control's missing transport must not fire a pooling banner.

    Live bug: `axis_summary` writes "" and the ledger writes None; counting
    either as a revision made every run containing Z0 read as Mixed.

    No `mcp_revision` in either manifest, deliberately. Extraction is
    first-hit-wins, so a manifest value short-circuits the axes and row paths
    entirely — and those are the only paths where an absence can appear. Every
    ledger written before the manifest extension is in exactly this state, so
    stating the value here would test the one case that cannot have the bug.
    """
    rows = (rows_for("A1", passes=1, mcp_spec_revision="2026-07-28",
                     axes={"mcp_revision": "2026-07-28"})
            + rows_for("Z0", passes=1, mcp_spec_revision=absent,
                       axes={"mcp_revision": absent if absent is not None else ""}))
    c = _cmp(_run("a", rows),
             _run("b", rows_for("A1", passes=1, mcp_spec_revision="2026-07-28",
                                axes={"mcp_revision": "2026-07-28"})))
    mcp = next(p for p in c.params if p.name == "mcp revision")
    assert not isinstance(mcp.values["a"], Mixed), (
        f"{absent!r} counted as a second revision: {mcp.values['a']}")
    assert mcp.values["a"] == "2026-07-28"
    assert not c.pooling_refused, [b.render() for b in c.pooling_breaks]


def test_an_arm_with_no_transport_at_all_reads_as_none() -> None:
    """Every arm lacking MCP is an absence, not an unknown.

    Distinct from the case above: there is no revision anywhere to fall back
    on, and the answer must still be a value rather than NOT_RECORDED — a
    shell-only run did have a transport story, and it was "there wasn't one".
    """
    rows = rows_for("C1", passes=1, mcp_spec_revision=None,
                    axes={"mcp_revision": ""})
    value, source = extract(_run("a", rows).report,
                            next(p for p in PARAMETERS
                                 if p.name == "mcp revision"))
    assert value == "none" and source == "axes"


def test_every_manifest_key_cmd_run_writes_has_a_parameter_row() -> None:
    """Drift guard: a new manifest field invisible to compare must fail loudly."""
    cli = Path(__file__).resolve().parents[1] / "src" / "harness" / "cli.py"
    tree = ast.parse(cli.read_text())
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name != "write_manifest":
            continue
        for kw in node.keywords:
            if kw.arg:
                keys.add(kw.arg)
    covered = {p.manifest_key for p in PARAMETERS if p.manifest_key} | MANIFEST_IGNORED
    missing = keys - covered
    assert not missing, (
        f"cmd_run writes {sorted(missing)} but PARAMETERS has no row for them. "
        "A comparison cannot see a parameter that has no Parameter row."
    )


def test_a_differing_target_is_named_but_does_not_refuse_pooling(
        tmp_path: Path) -> None:
    """Two field runs of the same tasks against different servers must compare.

    Comparing targets is the point of the workflow; marking `target` as a
    pooling boundary would exit 3 on the feature's own primary use case. The
    tasks are identical, so pairing within core stays valid.
    """
    from harness.cli import main

    digest = "same-tasks-digest"
    a_rows = [row(arm="A1", outcome="pass", core_id=f"c{i}",
                  task_id=f"c{i}-a", model="m") for i in range(4)]
    b_rows = [row(arm="A1", outcome="fail", core_id=f"c{i}",
                  task_id=f"c{i}-b", model="m") for i in range(4)]
    shared = dict(model="m", pack_digest=digest, pack_name="api")
    a = _ledger(tmp_path / "a", a_rows, id="a",
                target="https://v1.example/mcp", pack_path="packs/v1.yaml",
                **shared)
    b = _ledger(tmp_path / "b", b_rows, id="b",
                target="https://v2.example/mcp", pack_path="packs/v2.yaml",
                **shared)
    assert main(["compare", str(a), str(b)]) == 0

    c = _cmp(
        _run("a", a_rows, target="https://v1.example/mcp",
             pack_name="api", pack_path="packs/v1.yaml", pack_digest=digest,
             model="m"),
        _run("b", b_rows, target="https://v2.example/mcp",
             pack_name="api", pack_path="packs/v2.yaml", pack_digest=digest,
             model="m"),
    )
    target = next(p for p in c.params if p.name == "target")
    assert target.differs
    assert not c.pooling_refused, [b.render() for b in c.pooling_breaks]
    contrast = c.contrast_for("A1", "b")
    assert contrast is not None and contrast.method == "paired-core"


def test_a_target_url_is_stored_without_credentials(tmp_path: Path) -> None:
    """A pack URL's userinfo and query must never reach manifest.json."""
    from harness.cli import _field_manifest_fields
    from harness.engine.taskpack import TaskPack

    pack = TaskPack.parse({
        "schema_version": 1,
        "pack": {"id": "secret-api", "report_class": "field"},
        "api": {
            "mcp": {
                "url": "https://user:s3cret@api.example/mcp?token=leak-me",
            },
        },
        "tasks": [{"id": "t1", "prompt": "q", "class": "R"}],
    })
    fields = _field_manifest_fields(pack, "packs/secret.yaml")
    store = ResultStore(tmp_path)
    store.write_manifest(id="cred-check", **fields)
    text = (tmp_path / "manifest.json").read_text()
    assert "s3cret" not in text
    assert "leak-me" not in text
    assert "user:" not in text
    assert "token=" not in text
    assert fields["target"] == "https://api.example/mcp"
    assert fields["pack_name"] == "secret-api"
    assert fields["pack_path"] == "packs/secret.yaml"


def test_a_controlled_run_has_no_target_parameter() -> None:
    """Rig manifests omit the keys — absent, not None — so compare reads
    NOT_RECORDED rather than inventing a difference between two controlled runs.
    """
    a = _run("a", rows_for("A1", passes=1), model="m", cores=4)
    b = _run("b", rows_for("A1", passes=1), model="m", cores=4)
    assert "target" not in a.report.manifest
    assert "pack_name" not in a.report.manifest
    assert "pack_path" not in a.report.manifest
    c = _cmp(a, b)
    for name in ("target", "pack name", "pack path"):
        row = next(p for p in c.params if p.name == name)
        assert row.values["a"] is NOT_RECORDED
        assert row.values["b"] is NOT_RECORDED
        assert not row.differs


# ---- pooling -------------------------------------------------------------

def test_a_differing_model_leads_with_a_stop_banner() -> None:
    a = _run("a", rows_for("A1", passes=1, model="m1"), model="m1")
    b = _run("b", rows_for("A1", passes=1, model="m2"), model="m2")
    c = _cmp(a, b)
    assert c.pooling_refused
    text = render_text(c)
    html = render_html(c)
    assert "REFUSING TO POOL" in text or "Refusing to pool" in text
    assert "model" in text and "m1" in text and "m2" in text
    assert "Refusing to pool" in html or "REFUSING TO POOL" in html


def test_comparison_still_renders_across_a_pooling_break() -> None:
    a = _run("a", rows_for("A1", passes=2, model="m1"), model="m1")
    b = _run("b", rows_for("A1", passes=1, fails=1, model="m2"), model="m2")
    c = _cmp(a, b)
    text = render_text(c)
    assert "A1" in text
    assert c.delta("b", "A1", "success") is not None


def test_a_cross_world_delta_is_marked_not_a_finding() -> None:
    a = _run("a", rows_for("A1", passes=4, model="m1"), model="m1", mde_pp=5.0)
    b = _run("b", rows_for("A1", passes=0, fails=4, model="m2"), model="m2",
             mde_pp=5.0)
    c = _cmp(a, b)
    contrast = c.contrast_for("A1", "b")
    assert contrast is not None
    assert contrast.cross_world
    assert not contrast.notable
    text = render_text(c)
    html = render_html(c)
    assert "‡" in text and "‡" in html


def test_skill_condition_is_checked_per_arm_not_per_run() -> None:
    """A run-level Mixed would always fire; the useful sentence is per arm."""
    a_rows = (rows_for("A1", passes=1, skill_condition="none")
              + rows_for("B1", passes=1, skill_condition="generated"))
    b_rows = (rows_for("A1", passes=1, skill_condition="none")
              + rows_for("B1", passes=1, skill_condition="authored"))
    c = _cmp(_run("a", a_rows), _run("b", b_rows))
    breaks = [b for b in c.pooling_breaks if b.parameter == "skill condition"]
    assert breaks and breaks[0].scope == "B1"
    assert "skill condition" not in {p.name for p in PARAMETERS}


# ---- renderers / anti-drift ----------------------------------------------

def test_text_and_html_agree_on_every_rate() -> None:
    a = _run("a", rows_for("A1", passes=3, fails=1) + rows_for("B1", passes=2))
    b = _run("b", rows_for("A1", passes=2, fails=2) + rows_for("B1", passes=1,
                                                                fails=1))
    c = _cmp(a, b)
    text = render_text(c)
    html = render_html(c)
    for label in c.labels:
        for arm in c.shared_arms:
            value = c.value(label, arm, "success")
            rendered = Comparison.fmt("success", value)
            assert rendered in text, f"{label}/{arm} {rendered} missing from text"
            assert rendered in html, f"{label}/{arm} {rendered} missing from html"


def test_text_and_html_agree_on_every_delta() -> None:
    a = _run("a", rows_for("A1", passes=3, fails=1))
    b = _run("b", rows_for("A1", passes=1, fails=3))
    c = _cmp(a, b)
    text = render_text(c)
    html = render_html(c)
    delta = c.delta("b", "A1", "success")
    rendered = Comparison.fmt_delta("success", delta)
    assert rendered in text and rendered in html


def test_html_has_no_external_requests() -> None:
    c = _cmp(_run("a", rows_for("A1", passes=1)),
             _run("b", rows_for("A1", passes=1)))
    html = standalone_html(c)
    external = [line for line in html.split('"')
                if line.startswith(("http://", "https://"))
                and "www.w3.org/2000/svg" not in line]
    assert not external, f"external references: {external[:3]}"


def test_html_declares_a_charset() -> None:
    c = _cmp(_run("a", rows_for("A1", passes=1)),
             _run("b", rows_for("A1", passes=1)))
    assert '<meta charset="utf-8">' in standalone_html(c)


def test_reference_run_is_named_in_the_header() -> None:
    c = _cmp(_run("alpha", rows_for("A1", passes=1)),
             _run("beta", rows_for("A1", passes=1)))
    text = render_text(c)
    html = render_html(c)
    assert "reference" in text and "alpha" in text
    assert "alpha" in html


def test_parameters_appear_before_results() -> None:
    a = _run("a", rows_for("A1", passes=1), difficulty="standard")
    b = _run("b", rows_for("A1", passes=1), difficulty="hard")
    c = _cmp(a, b)
    text = render_text(c)
    html = render_html(c)
    assert text.index("what differs") < text.index("success by arm")
    assert html.index("What differs") < html.index("Head to head")


def test_score_table_is_suppressed_when_arm_sets_differ() -> None:
    a = _run("a", rows_for("A1", passes=2) + rows_for("B1", passes=2))
    b = _run("b", rows_for("A1", passes=2))
    c = _cmp(a, b)
    assert not c.score_comparable
    text = render_text(c, keys=("success", "score"))
    html = render_html(c, keys=("success", "score"))
    assert "not comparable" in text.lower() or "SCORE is not comparable" in text
    assert "not comparable" in html


def test_glossary_defines_the_comparison_vocabulary() -> None:
    """The terms the comparison introduces must be explained somewhere."""
    for name in ("reference run", "Δ / delta", "shared arm", "not compared",
                 "not recorded", "same world", "unpaired comparison",
                 "cross-world delta", "cross-run MDE", "parameter diff",
                 "confidence interval"):
        assert lookup(name) is not None, f"missing glossary term: {name}"


def test_every_column_header_resolves_to_a_glossary_entry() -> None:
    """A header that explains itself on hover, or does not claim to.

    `_th` degrades silently to a plain cell when the term is unknown, so a
    typo'd or unregistered name costs the tooltip without costing a test. The
    terms are read out of the source rather than listed here — a hardcoded list
    cannot notice a header added next week, which is exactly how the `success`
    column lost its definition.
    """
    source = (Path(__file__).resolve().parents[1] / "src" / "harness"
              / "engine" / "comparison_html.py").read_text()
    used = re.findall(r'_th\("([^"]+)"(?:,\s*"([^"]+)")?\)', source)
    assert used, "no _th calls found — has the renderer been restructured?"
    missing = sorted({term or label for label, term in used
                      if lookup(term or label) is None})
    assert not missing, f"column headers with no glossary entry: {missing}"


def test_head_to_head_defers_to_the_contrast_not_the_noise_floor() -> None:
    """The arrow and the mark must not contradict each other.

    The discriminating case, and the one that shipped wrong: a gap comfortably
    above the combined noise floor whose interval still spans zero. A
    head-to-head that checked only the MDE drew an up arrow three lines above a
    contrast table saying the difference was not resolvable. Both readings
    cannot be on the same page, so `unresolved` asks the contrast.

    A large MDE would let a floor-only check reach the right answer by luck, so
    the floor here is deliberately tiny.
    """
    a = _run("a", rows_for("A1", passes=3, fails=3), mde_pp=1.0, **_WORLD)
    b = _run("b", rows_for("A1", passes=5, fails=1), mde_pp=1.0,
             seed=2, cores=4, fan_out=8, difficulty="standard")
    c = _cmp(a, b)

    contrast = c.contrast_for("A1", "b")
    assert contrast is not None
    # The gap is real-looking and far above the floor...
    assert c.delta("b", "A1", "success") == pytest.approx(1 / 3, abs=0.01)
    assert not contrast.below_mde
    # ...but the interval admits no difference, so it is not a finding.
    assert contrast.spans_zero and not contrast.notable
    assert c.unresolved("b", "A1", "success"), (
        "head-to-head called a gap the contrast refuses to call")
    assert "↑" not in _delta_line(render_text(c), "A1")


def _delta_line(text: str, arm: str) -> str:
    """The success table's row for one arm."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("  success by arm"))
    return next(l for l in lines[start:start + 8] if l.strip().startswith(arm))


# ---- csv -----------------------------------------------------------------

def test_csv_writes_three_files_with_a_run_column(tmp_path: Path) -> None:
    a = _run("a", rows_for("A1", passes=1) + rows_for("B1", passes=1))
    b = _run("b", rows_for("A1", passes=1))
    written = write_csv(_cmp(a, b), tmp_path)
    names = {p.name for p in written}
    assert names == {"arms.csv", "params.csv", "rows.csv"}
    for path in written:
        with path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert "run" in reader.fieldnames
            assert list(reader)  # non-empty


def test_rows_csv_survives_ledgers_with_different_columns(tmp_path: Path) -> None:
    """Must not reproduce the report --csv first-row fieldnames bug."""
    a_rows = rows_for("A1", passes=1, axes={"schema_detail": "terse"})
    b_rows = rows_for("A1", passes=1)  # no axes
    written = {p.name: p for p in write_csv(_cmp(_run("a", a_rows),
                                                 _run("b", b_rows)), tmp_path)}
    with written["rows.csv"].open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert any(r.get("axis.schema_detail") == "terse" for r in rows)
    assert any(r["run"] == "b" for r in rows)


def test_params_csv_flags_which_differ(tmp_path: Path) -> None:
    a = _run("a", rows_for("A1", passes=1), difficulty="standard")
    b = _run("b", rows_for("A1", passes=1), difficulty="hard")
    path = write_csv(_cmp(a, b), tmp_path)[1]  # params.csv
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    flag = next(r for r in rows if r["run"] == "__differs__")
    assert flag["difficulty"] == "yes"


def test_arms_csv_includes_arms_not_in_the_head_to_head(tmp_path: Path) -> None:
    a = _run("a", rows_for("A1", passes=1) + rows_for("B1", passes=1))
    b = _run("b", rows_for("A1", passes=1))
    path = write_csv(_cmp(a, b), tmp_path)[0]
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    exclusive = [r for r in rows if r["arm"] == "B1"]
    assert exclusive and exclusive[0]["shared"] == "no"


# ---- cli -----------------------------------------------------------------

def _ledger(dir_path: Path, rows: list[dict], **manifest) -> Path:
    store = ResultStore(dir_path)
    store.write_manifest(**manifest)
    for r in rows:
        with (dir_path / LEDGER).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
    return dir_path


def test_compare_needs_two_directories() -> None:
    from harness.cli import main
    assert main(["compare", "results/matrix-10"]) == 2


def test_compare_on_a_missing_directory_does_not_create_it(tmp_path: Path) -> None:
    """ResultStore mkdirs — a typo must not leave junk behind."""
    from harness.cli import main
    missing = tmp_path / "does-not-exist"
    other = _ledger(tmp_path / "other", rows_for("A1", passes=1), id="other",
                    model="m", cores=1)
    assert main(["compare", str(missing), str(other)]) == 1
    assert not missing.exists()


def test_nonzero_across_a_pooling_break_zero_with_allow(tmp_path: Path) -> None:
    from harness.cli import main
    a = _ledger(tmp_path / "a", rows_for("A1", passes=2, model="m1"),
                id="a", model="m1", cores=2)
    b = _ledger(tmp_path / "b", rows_for("A1", passes=1, fails=1, model="m2"),
                id="b", model="m2", cores=2)
    assert main(["compare", str(a), str(b)]) == 3
    assert main(["compare", str(a), str(b), "--allow-cross-world"]) == 0


def test_mde_pp_is_injected_per_run(tmp_path: Path) -> None:
    """Two manifests with different cores → different report.mde_pp."""
    from harness.cli import _build_report
    a = _ledger(tmp_path / "a", rows_for("A1", passes=1), id="a", model="m",
                cores=4, repeats=1)
    b = _ledger(tmp_path / "b", rows_for("A1", passes=1), id="b", model="m",
                cores=40, repeats=1)
    ra = _build_report(ResultStore(a))
    rb = _build_report(ResultStore(b))
    assert ra.mde_pp is not None and rb.mde_pp is not None
    assert ra.mde_pp > rb.mde_pp


def test_more_than_eight_runs_is_refused() -> None:
    runs = [_run(f"r{i}", rows_for("A1", passes=1)) for i in range(9)]
    with pytest.raises(ComparisonError, match="palette"):
        Comparison(runs=runs)


def test_label_runs_disambiguates_duplicate_ids() -> None:
    entries = [("results/a", {"id": "phase-0"}),
               ("results/b", {"id": "phase-0"})]
    labels = label_runs(entries)
    assert len(set(labels)) == 2
    assert all("phase-0" in label for label in labels)


# ---- pack digest ---------------------------------------------------------

def _generated_tasks(seed: int, cores: int = 4, difficulty: str = "hard"):
    """The task list `cmd_run` would hand to `_pack_digest`."""
    from harness.engine.taskpack import TaskPack
    from harness.experiment.domain import WorldShape, build_world, shape_for_cores
    from harness.experiment.tasks import build_pack

    shape = shape_for_cores(cores, WorldShape(episodes_per_season=8))
    pack = TaskPack.parse(build_pack(build_world(seed, shape), cores=cores,
                                     seed=seed, difficulty=difficulty))
    return list(pack.tasks)


def test_pack_digest_separates_worlds_that_share_task_ids() -> None:
    """Task ids are as positional as core ids — the digest must not trust them.

    Live bug: the digest hashed only `(id, core_id, class, answerable)`. Seed 1
    and seed 2 both generate a task called `core-000-R`, asking about different
    shows, so those four fields are byte-identical across the two worlds. The
    digest collided — and because `world_key` *prefers* the digest, the
    collision overrode the `(seed, cores, fan_out, difficulty)` tuple that
    would have correctly refused to pair. A wrong digest is worse than none.
    """
    from harness.cli import _pack_digest

    one, two = _generated_tasks(1), _generated_tasks(2)
    assert [t.id for t in one] == [t.id for t in two], (
        "premise gone: ids are no longer positional, so this test is moot")
    assert _pack_digest(one) != _pack_digest(two)


def test_pack_digest_is_stable_and_order_independent() -> None:
    """Same world, same address — whatever order the tasks arrive in."""
    from harness.cli import _pack_digest

    tasks = _generated_tasks(1)
    assert _pack_digest(tasks) == _pack_digest(list(reversed(tasks)))
    assert _pack_digest(tasks) == _pack_digest(_generated_tasks(1))


@pytest.mark.parametrize("changed", [
    pytest.param(lambda: _generated_tasks(1, difficulty="standard"), id="difficulty"),
    pytest.param(lambda: _generated_tasks(1, cores=6), id="cores"),
    pytest.param(lambda: _generated_tasks(1)[:-1], id="filtered-subset"),
])
def test_pack_digest_notices_a_different_task_set(changed) -> None:
    """`--classes` and `--max-tasks` cut the set without touching a world
    parameter, so the digest is the only thing that can see it."""
    from harness.cli import _pack_digest

    assert _pack_digest(_generated_tasks(1)) != _pack_digest(changed())
