"""Drafting a pack from a surface. The output must load, and must be safe."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from harness.engine.generate import ApiSpec, Operation, load_spec
from harness.engine.taskpack import TaskPack
from harness.scaffold import build, is_read, to_yaml

ROOT = Path(__file__).resolve().parent.parent


def _op(operation_id: str, method: str = "get", path: str | None = None) -> Operation:
    return Operation(operation_id=operation_id, method=method,
                     path=path or f"/{operation_id}", summary="s",
                     description="d", parameters=(), request_body=None,
                     responses={})


def _spec(*ops: Operation, source: str = "openapi") -> ApiSpec:
    return ApiSpec(title="T", version="1", operations=tuple(ops), raw={},
                   source=source)


# ---- read/write classification --------------------------------------------

def test_http_verbs_decide_for_an_openapi_surface() -> None:
    assert is_read(_op("list_things", "get"))
    assert not is_read(_op("make_thing", "post"))


def test_mcp_falls_back_to_the_name() -> None:
    """`spec_from_tools` stamps every tool POST, so the verb says nothing."""
    assert is_read(_op("list_things", "post"), source="mcp")
    assert not is_read(_op("report_error", "post"), source="mcp")


def test_a_read_prefix_beats_a_mutating_noun() -> None:
    """`get_knowledge_base_report` is a read whose noun is a verb."""
    assert is_read(_op("get_knowledge_base_report", "post"), source="mcp")


# ---- the generated pack ----------------------------------------------------

def test_the_output_loads_without_hand_editing() -> None:
    """Stubs unfilled is fine; a pack that will not parse is not."""
    spec = _spec(_op("list_things"), _op("get_thing"), _op("delete_thing", "delete"))
    pack = TaskPack.parse(build(spec, pack_id="p"))
    assert pack.pack.id == "p"
    assert pack.tasks


def test_writes_are_skipped_so_the_pack_is_safe_as_generated() -> None:
    """`writes_enabled: false` plus a mutating task is a pack that cannot load."""
    spec = _spec(_op("list_things"), _op("delete_thing", "delete"),
                 _op("create_thing", "post"))
    raw = build(spec, pack_id="p")

    assert raw["safety"]["writes_enabled"] is False
    assert all(t["class"] == "R" for t in raw["tasks"])
    TaskPack.parse(raw)  # must not raise


def test_every_unexercised_operation_is_forbidden() -> None:
    """Untasked is not unreachable — an arm can still find and call it."""
    spec = _spec(_op("list_things"), _op("delete_thing", "delete"),
                 _op("create_thing", "post"))
    raw = build(spec, pack_id="p")
    assert set(raw["safety"]["forbidden_calls"]) == {"delete_thing", "create_thing"}


def test_nothing_is_graded_and_that_is_deliberate() -> None:
    """A stub that asserted something plausible would look finished."""
    raw = build(_spec(_op("list_things")), pack_id="p")
    assert all(t["grade"] == [] for t in raw["tasks"])
    assert all("TODO" in t["prompt"] for t in raw["tasks"])


def test_unanswerables_are_included_at_roughly_the_prescribed_share() -> None:
    """Without them a pack cannot measure fabrication at all."""
    spec = _spec(*[_op(f"get_thing_{i}") for i in range(17)])
    raw = build(spec, pack_id="p")
    unanswerable = [t for t in raw["tasks"] if not t["answerable"]]
    assert unanswerable
    assert 0.10 <= len(unanswerable) / len(raw["tasks"]) <= 0.25


def test_a_read_only_surface_still_gets_an_unanswerable() -> None:
    raw = build(_spec(_op("list_things")), pack_id="p")
    assert any(not t["answerable"] for t in raw["tasks"])


def test_field_is_the_only_report_class_a_draft_can_claim() -> None:
    """Contamination is uncontrolled on a real API; `controlled` would lie."""
    assert build(_spec(_op("x")), pack_id="p")["pack"]["report_class"] == "field"


# ---- serialisation ---------------------------------------------------------

def test_yaml_round_trips_through_the_loader() -> None:
    import yaml

    raw = build(_spec(_op("list_things"), _op("delete_thing", "delete")),
                pack_id="p", mcp_url="https://example.test/mcp")
    reloaded = yaml.safe_load(to_yaml(raw))
    assert TaskPack.parse(reloaded).pack.id == "p"
    assert reloaded["api"]["mcp"]["spec_revision"] == "auto"


def test_the_header_says_what_to_do_next() -> None:
    text = to_yaml(build(_spec(_op("x")), pack_id="p"))
    assert "harness run --pack" in text
    assert "no grader means no result" in text


# ---- the shipped template --------------------------------------------------

def test_the_init_template_is_a_valid_pack() -> None:
    """It is the first file a new user edits; it must not start broken."""
    import yaml

    from harness.cli import _PACK_TEMPLATE

    TaskPack.parse(yaml.safe_load(_PACK_TEMPLATE))


@pytest.mark.parametrize(
    "skill", ["harness-lab", "harness-field-pack", "harness-insights"])
def test_agent_skills_ship_inside_the_package(skill: str) -> None:
    """`harness init` reads these out of the wheel, not out of a checkout."""
    from importlib import resources

    path = resources.files("harness") / "agent_skills" / skill / "SKILL.md"
    assert path.is_file()
    assert "name:" in path.read_text()


def test_skills_do_not_cite_docs_that_are_not_shipped() -> None:
    """A skill lands in a project that has the wheel, not this checkout.

    Its doc pointers have to resolve there, so they may name only the five
    guides under `docs/` — never a reference contract, which lives in the
    gitignored `archive/` and reaches no customer.
    """
    from importlib import resources

    shipped = {p.name for p in (ROOT / "docs").glob("*.md")}
    root = resources.files("harness") / "agent_skills"
    for skill in root.iterdir():
        if not skill.is_dir():
            continue
        text = (skill / "SKILL.md").read_text()
        for cited in re.findall(r"docs/([\w\-]+\.md)", text):
            assert cited in shipped, (
                f"{skill.name} cites docs/{cited}, which is not shipped")
        assert "archive/" not in text, f"{skill.name} cites the internal archive"
