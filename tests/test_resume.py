"""`--resume` reproduces the matrix it is resuming.

A resume is the one command that writes into a results directory it did not
create. Everything here is about that seam: the rows on disk were produced by
an earlier invocation whose flags are gone from the shell history, and the only
surviving record of them is `manifest.json`.
"""

from __future__ import annotations

import argparse
import json

from harness.cli import _RESUME_INHERITED, _inherit_run_config, build_parser


def parse(*argv: str) -> argparse.Namespace:
    return build_parser().parse_args(["run", *argv])


# The matrix-40 manifest, trimmed to the fields under test.
MANIFEST = dict(
    created_at="2026-08-05T18:00:00+00:00",
    id="matrix-40", model="gpt-5.6-luna", provider="openai",
    presets=["Z0", "Z1", "A1", "A2", "B1", "B2", "C1", "D1", "D2"],
    cores=40, repeats=3, seed=1, surface_size=0, fan_out=8,
    reasoning_effort="low", difficulty="standard", temperature=0.0,
    caching="off", max_turns=12, schema_detail="standard",
    response_shape="as-is", error_detail="field-scoped", doc_budget="standard",
    mcp_revision="2026-07-28", sweep_error_detail=[], classes=[], max_tasks=None,
)


def test_bare_resume_takes_its_shape_from_the_manifest() -> None:
    """`--out DIR --id X --resume` and nothing else must still be matrix-40.

    This is the invocation an operator actually types after a crash, and every
    other flag is at its argparse default — none of which describe the matrix
    on disk.
    """
    args = parse("--out", "results/matrix-40", "--id", "matrix-40", "--resume")
    changed = _inherit_run_config(args, MANIFEST)

    assert args.cores == 40, "a defaulted --cores reseeds the world"
    assert args.repeats == 3
    assert args.model == "gpt-5.6-luna"
    assert args.presets == MANIFEST["presets"]
    assert changed, "silently correcting the flags is the bug, not the fix"
    assert any("cores" in line for line in changed)


def test_matching_flags_report_nothing() -> None:
    """Passing the run's real parameters back is not a disagreement."""
    args = parse(
        "--out", "results/matrix-40", "--id", "matrix-40", "--resume",
        "--model", "gpt-5.6-luna", "--cores", "40", "--repeats", "3",
        "--presets", *MANIFEST["presets"],
    )
    assert _inherit_run_config(args, MANIFEST) == []


def test_flags_that_would_cross_a_pooling_boundary_lose() -> None:
    """model and mcp_revision are pooling keys; the ledger cannot hold both."""
    args = parse("--out", "d", "--resume",
                 "--model", "gpt-5.6-sol", "--mcp-revision", "legacy")
    _inherit_run_config(args, MANIFEST)
    assert args.model == "gpt-5.6-luna"
    assert args.mcp_revision == "2026-07-28"


def test_concurrency_is_not_inherited() -> None:
    """Speed is the operator's call on every attempt; it shapes no result."""
    assert "concurrency" not in _RESUME_INHERITED
    args = parse("--out", "d", "--resume", "--concurrency", "24")
    _inherit_run_config(args, MANIFEST)
    assert args.concurrency == 24


def test_older_manifests_leave_unknown_fields_alone() -> None:
    """A manifest predating a flag must not reset that flag to its default."""
    args = parse("--out", "d", "--resume", "--cores", "40", "--max-turns", "30")
    changed = _inherit_run_config(args, {"model": "gpt-5.6-luna", "cores": 40})
    assert args.max_turns == 30
    assert changed == []


def test_empty_and_absent_list_flags_are_the_same_thing() -> None:
    """`classes: []` in the manifest vs `None` from argparse is not a delta."""
    args = parse("--out", "d", "--resume", "--cores", "40", "--repeats", "3",
                 "--presets", *MANIFEST["presets"])
    changed = _inherit_run_config(args, MANIFEST)
    assert changed == []
    assert args.classes is None


def test_every_inherited_field_is_a_real_run_argument() -> None:
    """Guards against a rename leaving a field silently un-inherited."""
    args = parse("--out", "d")
    for field in _RESUME_INHERITED:
        assert hasattr(args, field), f"{field} is not a `harness run` argument"


def test_a_drifted_task_pack_refuses_rather_than_appends(tmp_path, monkeypatch,
                                                         capsys) -> None:
    """Matching parameters are not proof of a matching world.

    A change to task generation between the original matrix and the resume
    yields the same `--cores`/`--seed` and different questions. Nothing
    downstream can see that, so it has to be caught before the first cell.
    """
    from harness import cli

    store_dir = tmp_path / "m"
    store_dir.mkdir()
    (store_dir / "manifest.json").write_text(json.dumps(
        {**MANIFEST, "cores": 2, "difficulty": "standard",
         "presets": ["Z0"], "repeats": 1,
         "pack_digest": "0000000000000000"}))
    (store_dir / "results.jsonl").write_text("")

    code = cli.main(["run", "--out", str(store_dir), "--id", "m", "--resume"])

    out = capsys.readouterr().out
    assert code == cli._EXIT_REFUSED
    assert "refusing to resume" in out
    assert "0000000000000000" in out


def test_a_matching_pack_digest_gets_past_the_check(tmp_path, capsys) -> None:
    """The guard must not block the resume it exists to protect."""
    from harness import cli
    from harness.engine.taskpack import TaskPack
    from harness.experiment.domain import WorldShape, build_world, shape_for_cores
    from harness.experiment.tasks import build_pack

    shape = shape_for_cores(2, WorldShape(episodes_per_season=8))
    pack = TaskPack.parse(build_pack(build_world(1, shape), cores=2, seed=1,
                                     difficulty="standard"))
    digest = cli._pack_digest(list(pack.tasks))

    store_dir = tmp_path / "m"
    store_dir.mkdir()
    (store_dir / "manifest.json").write_text(json.dumps(
        {**MANIFEST, "cores": 2, "difficulty": "standard", "surface_size": 0,
         "presets": ["Z0"], "repeats": 1, "pack_digest": digest}))
    (store_dir / "results.jsonl").write_text("")

    # Declines at the spend prompt, which is past the digest check.
    code = cli.main(["run", "--out", str(store_dir), "--id", "m", "--resume"])

    out = capsys.readouterr().out
    assert "refusing to resume" not in out
    assert code != cli._EXIT_REFUSED
