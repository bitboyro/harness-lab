"""`harness doctor`, and the two ways in.

The environment check is what someone runs when nothing works, so it has to
work when nothing works: no provider stack, no network, no key.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness import doctor

ROOT = Path(__file__).resolve().parent.parent


# ---- the checks ------------------------------------------------------------

def test_every_check_says_what_it_blocks() -> None:
    """A bare 'curl: missing' makes a reader guess whether that matters."""
    for check in doctor.run():
        if check.status != doctor.OK:
            assert check.blocks, f"{check.name} is not ok but explains nothing"


def test_the_required_ones_pass_in_this_environment() -> None:
    by_name = {c.name: c for c in doctor.run()}
    for name in ("python", "harness", "pydantic", "yaml"):
        assert by_name[name].status == doctor.OK, by_name[name]


def test_an_api_key_is_never_printed(monkeypatch) -> None:
    """Names in the report, values never — this ends up in screenshots."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-appear")
    text = doctor.render(doctor.run())
    assert "sk-should-not-appear" not in text
    assert "OPENAI_API_KEY" in text


def test_a_missing_optional_does_not_read_as_broken(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    checks = doctor.run()
    assert not any(c.status == doctor.MISSING for c in checks)
    assert "Ready." in doctor.render(checks)


def test_render_survives_a_missing_requirement() -> None:
    checks = [doctor.Check("python", doctor.MISSING, "3.9.6", "everything")]
    text = doctor.render(checks)
    assert "MISS" in text and "everything" in text
    assert "will not run" in text


# ---- the command ------------------------------------------------------------

def test_doctor_exits_zero_when_nothing_required_is_missing(capsys) -> None:
    from harness.cli import main

    assert main(["doctor"]) == 0
    assert "python" in capsys.readouterr().out


def test_doctor_needs_no_provider_and_no_network() -> None:
    """It is run precisely when the install is broken."""
    source = (ROOT / "src" / "harness" / "doctor.py").read_text()
    tree = ast.parse(source)
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import) for alias in node.names
    }
    assert not (imported & {"openai", "anthropic", "requests", "httpx", "urllib"})


# ---- two ways in, and no third ---------------------------------------------

@pytest.mark.parametrize("argv", [
    [sys.executable, "-m", "harness", "--version"],
    [sys.executable, "-m", "harness", "lint", "--demo"],
])
def test_python_dash_m_harness_works(argv) -> None:
    """The console script is not always on PATH; this always is."""
    done = subprocess.run(argv, capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done.stderr


def test_the_two_entry_points_are_the_same_function() -> None:
    import harness.__main__ as dunder
    from harness.cli import main

    assert dunder.main is main


# ---- the installer ----------------------------------------------------------

def test_installer_parses_on_old_python() -> None:
    """It exists to tell a 3.9 user to upgrade, so it must parse on 3.9.

    A SyntaxError instead of the explanation is the one failure this script
    cannot have.
    """
    source = (ROOT / "install.py").read_text()
    compile(source, "install.py", "exec")

    tree = ast.parse(source)
    for node in ast.walk(tree):
        # Walrus, match, and f-string nesting are the usual ways a "portable"
        # script quietly stops being portable.
        assert not isinstance(node, ast.NamedExpr), "walrus is 3.8+"
        assert not isinstance(node, getattr(ast, "Match", ()) or ()), "match is 3.10+"


def test_installer_imports_only_the_standard_library() -> None:
    tree = ast.parse((ROOT / "install.py").read_text())
    roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import) for alias in node.names
    }
    assert roots <= {"glob", "json", "os", "subprocess", "sys", "tempfile", "pip"}


def test_installer_never_handles_a_token() -> None:
    """The repo is public, so the download is anonymous and takes no credential.

    The shell installer this replaced put a GITHUB_TOKEN in a URL, where every
    process on the machine can read it out of the process list. Nothing here
    should read a token, embed one, or accept one as an argument — and if the
    repo ever goes private, this test is the reminder to add auth deliberately
    rather than by pasting a token into the URL again.
    """
    tree = ast.parse((ROOT / "install.py").read_text())

    # Docstrings are exempt: this file *explains* why it takes no token, and a
    # check that forbids naming the thing would forbid documenting the rule.
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    literals = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    for secret in ("GITHUB_TOKEN", "GH_TOKEN", "Authorization", "--token"):
        assert not any(secret in text for text in literals), \
            f"install.py handles {secret} in code"

    # The only environment variable it may read is PATH.
    env_reads = {
        node.slice.value for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "environ"
    } | {
        node.args[0].value for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get" and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "environ" and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert env_reads <= {"PATH"}, f"install.py reads {env_reads - {'PATH'}}"


def _installer():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_installer", ROOT / "install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installer_downloads_the_wheel_asset(monkeypatch, tmp_path) -> None:
    """Picks the wheel out of a release, and writes exactly those bytes."""
    installer = _installer()
    payload = json.dumps({"assets": [
        {"name": "harness-lab-0.0.1.zip", "size": 9,
         "browser_download_url": "https://example.invalid/bundle.zip"},
        {"name": "harness_lab-0.0.1-py3-none-any.whl", "size": 5,
         "browser_download_url": "https://example.invalid/w.whl"},
    ]}).encode()

    seen = []

    def fake_get(url):
        seen.append(url)
        return (payload if "api.github.com" in url else b"WHEEL"), None

    monkeypatch.setattr(installer, "_get", fake_get)
    path, problem = installer.download_wheel(None)

    assert problem is None
    assert path.endswith("harness_lab-0.0.1-py3-none-any.whl")
    assert Path(path).read_bytes() == b"WHEEL"
    # The zip asset must not be mistaken for the wheel.
    assert seen[1] == "https://example.invalid/w.whl"


def test_installer_download_honours_a_tag(monkeypatch) -> None:
    installer = _installer()
    seen = []
    monkeypatch.setattr(installer, "_get",
                        lambda url: (seen.append(url), (b"{}", None))[1])
    installer.download_wheel("v0.0.1")
    assert seen[0].endswith("/releases/tags/v0.0.1")


def test_installer_download_failure_names_the_way_out(monkeypatch) -> None:
    """A 404 here means no release exists, which is not obvious from the error."""
    installer = _installer()
    monkeypatch.setattr(installer, "_get", lambda url: (None, "HTTP Error 404"))
    wheel, problem = installer.download_wheel(None)
    assert wheel is None
    assert "./build.sh" in problem and "rate limit" in problem


def test_installer_reports_before_it_installs() -> None:
    """--check must never mutate anything."""
    done = subprocess.run(
        [sys.executable, str(ROOT / "install.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done.stderr
    assert "Checking this machine" in done.stdout
    assert "install nothing" in done.stdout or "Re-run without --check" in done.stdout
