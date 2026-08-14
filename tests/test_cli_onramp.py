"""The first five minutes: the paths a new user hits before anything works."""

from __future__ import annotations

import json

import pytest

from harness.cli import main
from harness.engine.generate import _is_url, _looks_like_yaml, load_spec


@pytest.fixture(autouse=True)
def _isolated_rule_registry():
    """`cmd_lint` registers the built-in rules into a module-level registry.

    Left behind, they run against every later test's spec — including one that
    passes `None` deliberately — so a test that only meant to lint the demo API
    fails an unrelated test in whichever order pytest happens to pick.
    """
    from harness.engine.lint import _REGISTRY

    saved = dict(_REGISTRY)
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(saved)


# ---- lint: free, no key, no file ------------------------------------------

def test_demo_lints_without_a_spec_or_a_key(capsys) -> None:
    """The free first command. It must not need a file or a credential."""
    assert main(["lint", "--demo"]) == 0
    out = capsys.readouterr().out
    assert "operations" in out
    assert "heuristic" in out  # the honesty footer survives


def test_lint_with_nothing_to_lint_says_what_to_pass(capsys) -> None:
    assert main(["lint"]) == 2
    assert "--demo" in capsys.readouterr().err


# ---- specs by URL ----------------------------------------------------------

def test_url_sources_are_recognised() -> None:
    assert _is_url("https://example.test/openapi.json")
    assert _is_url("http://example.test/openapi.json")
    assert not _is_url("/tmp/openapi.json")


def test_format_is_decided_by_the_body_not_the_extension() -> None:
    """A served spec has no extension, and plenty arrive as text/plain."""
    assert _looks_like_yaml("openapi: 3.1.0\n")
    assert not _looks_like_yaml('{"openapi": "3.1.0"}')
    assert not _looks_like_yaml('  \n  [1]')


def test_a_url_spec_is_fetched_and_parsed(monkeypatch) -> None:
    doc = {"openapi": "3.1.0", "info": {"title": "Remote", "version": "9"},
           "paths": {"/things": {"get": {"operationId": "list_things"}}}}
    monkeypatch.setattr("harness.engine.generate._fetch",
                        lambda url, timeout=30.0: json.dumps(doc))

    spec = load_spec("https://example.test/openapi.json")
    assert spec.title == "Remote"
    assert [op.operation_id for op in spec.operations] == ["list_things"]


# ---- operator mistakes are messages, not tracebacks -----------------------

def test_an_unpriced_model_is_a_message_and_leaves_nothing_behind(
        tmp_path, capsys) -> None:
    """A rejected run must not create the directory it was going to fill.

    An empty `traces/` beside no ledger reads like a run that died, which sends
    a reader looking for a crash that never happened.
    """
    out = tmp_path / "results"
    code = main(["run", "--out", str(out), "--id", "x", "--yes",
                 "--model", "no-such-model-at-all"])

    assert code == 40
    assert "no price on record" in capsys.readouterr().err
    assert not out.exists()


def test_a_broken_pack_is_a_message_not_a_traceback(tmp_path, capsys) -> None:
    pack = tmp_path / "bad.yaml"
    pack.write_text("schema_version: 1\npack: {id: x}\n")

    assert main(["run", "--pack", str(pack), "--out", str(tmp_path / "r"),
                 "--id", "x", "--yes"]) == 40
    assert "Traceback" not in capsys.readouterr().err


# ---- unattended -----------------------------------------------------------

def test_a_non_tty_is_told_about_yes(monkeypatch, capsys) -> None:
    """A bare 'aborted' in CI reads like the run decided against itself."""
    from harness import cli

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    assert cli._confirm() is False
    assert "--yes" in capsys.readouterr().err


# ---- profiles --------------------------------------------------------------

@pytest.mark.parametrize("profile,expected", [
    ("--smoke", ["Z0", "A1", "D1"]),
    ("--probe", ["Z0", "A1", "A2", "C1", "D1"]),
])
def test_profiles_pick_arms_without_overriding_an_explicit_choice(
        profile, expected) -> None:
    from harness.cli import _apply_probe_profile, _apply_smoke_profile, build_parser

    apply = _apply_smoke_profile if profile == "--smoke" else _apply_probe_profile

    args = build_parser().parse_args(["run", profile])
    apply(args)
    assert args.presets == expected

    chosen = build_parser().parse_args(["run", profile, "--presets", "B1"])
    apply(chosen)
    assert chosen.presets == ["B1"], "an explicit --presets must win"


def test_smoke_with_plan_keeps_smoke_cost_envelope() -> None:
    """Plan base.repeats must not undo --smoke after looking like a CLI default."""
    from harness.cli import (
        _apply_plan, _apply_smoke_profile, _pin_profile_envelopes, build_parser,
    )

    args = build_parser().parse_args([
        "run", "--smoke", "--plan", "plans/baseline-experiment-80.yaml",
        "--presets", "Z-cheat",
    ])
    _apply_smoke_profile(args)
    _apply_plan(args)
    _pin_profile_envelopes(args)
    assert args.repeats == 1
    assert args.cores == 2
    assert args.max_tasks == 4
    assert args.presets == ["Z-cheat"]
