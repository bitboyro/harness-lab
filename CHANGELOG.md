# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [semver](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Documentation restructured around readers rather than project chronology:
  five task-oriented guides under `docs/`, four contracts under
  `docs/reference/`, and three files at the root. Superseded design records are
  kept on the `archive/p0-contracts` branch.
- Code now cites documentation by **slug anchor** instead of section number. A
  section number drifts silently on every edit; a renamed heading now fails
  `tests/test_docs.py` loudly. Decision IDs (`F1`–`F4`, `G1`–`G13`, `O1`–`O8`)
  are treated as a stable API and checked.

## [0.1.0] — 2026-08-08

First tagged release.

### Added

- **`harness lint`** — static agent-readiness scorecard over an OpenAPI document
  or a live URL. Free, needs no API key. `--demo` lints the built-in API.
- **`harness run`** — one command and one execution path for both the controlled
  matrix and a live target. `--pack` selects a real API; `--probe` is a
  first-contact profile; `--smoke` proves the pipeline for about $0.05.
- **`harness scaffold`** — drafts a task pack from a live MCP server or an
  OpenAPI document. Reads only, `forbidden_calls` pre-filled, and deliberately
  ungraded: a stub asserting something plausible would look finished.
- **`harness init`** — installs the agent skills into a project
  (`--agent claude|cursor|both`), so a coding agent can drive the tool for
  someone who never cloned this repo.
- **`harness transcript`** and **`run --stream`** — every message to and from the
  model, every tool call with arguments, every result; replayed from a stored
  trace or watched live.
- **`harness report` / `compare` / `progress` / `plan` / `rig`** — reporting,
  N-run diffs with pooling refusals, live progress, cost projection with an
  approval gate, and rig sizing against a target MDE.
- Single-file build (`build.sh`) and a `curl | sh` installer.

### Notes on this release

- **Field mode reaches everything the matrix does.** It previously ran through a
  separate command that had no ledger, no concurrency, no resume and no report.
  There is no `harness probe`; it is `harness run --pack`.
- **A `.pyz`, not a frozen binary.** The sandbox arms execute model-written
  Python via `sys.executable`, which under PyInstaller resolves to the frozen
  executable — those arms would break, and break as ordinary failure rows rather
  than as an error. The `.pyz` keeps a real interpreter, and is therefore built
  per platform.
- **Metrics are unvalidated in field mode**, and 0 of 8 lint rules have a
  measured effect size. Both are printed on every artifact.
