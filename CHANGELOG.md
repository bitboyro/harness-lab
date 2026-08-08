# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [semver](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`harness-lab` skill** — the one that fires on "what is this", "which
  command do I run", or an error. It checks the install, picks a target, walks
  the cost ladder, and carries the refusals into whatever the agent reports:
  a lead under the MDE is a tie, a probe cannot crown a winner, and no run
  spends without the user's approval. `harness init` installs it alongside
  `harness-field-pack` and `harness-insights`; it copies whatever it finds, so
  a new skill needs no CLI change.

### Changed

- Documentation restructured around readers rather than project chronology:
  five task-oriented guides under `docs/`, and two files at the root.
- Code now cites documentation by **slug anchor** instead of section number. A
  section number drifts silently on every edit; a renamed heading now fails
  `tests/test_docs.py` loudly. Decision IDs (`F1`–`F4`, `G1`–`G13`, `O1`–`O8`)
  are treated as a stable API and checked.
- **Documentation is now the five guides, and nothing else.** The research
  design and internal planning are no longer distributed. They remain current
  and load-bearing where they live — the `Contract:` docstrings throughout the
  source still cite them by anchor, so a reader of the code will see references
  to material they do not have. That is deliberate rather than an oversight.
  Two tests hold the line: doc citations are checked in full wherever the
  originals are present and skipped where they are not, and no shipped guide or
  skill may link to a file the recipient was not given.
- `harness-field-pack` pointed at four documentation files that the
  restructure had deleted.

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
- **`harness doctor`** — reports Python, dependencies, credentials, `curl`,
  `git` and disk, and for anything missing says what that specific thing blocks.
  Imports no provider SDK and touches no network, because it is what you run
  when the install is broken.
- **`python -m harness`** alongside the `harness` console script. Two ways in
  and no third; the module form works when PATH does not.
- `build.sh` (wheel + a hand-off bundle) and `install.py`, an installer that
  runs on any Python 3 so an interpreter too old to run harness still gets an
  explanation instead of a `SyntaxError`.

### Notes on this release

- **Field mode reaches everything the matrix does.** It previously ran through a
  separate command that had no ledger, no concurrency, no resume and no report.
  There is no `harness probe`; it is `harness run --pack`.
- **A wheel, not a bundled single file.** Two single-file approaches were built
  and discarded. A frozen binary breaks the sandbox arms, which execute
  model-written Python via `sys.executable` — under PyInstaller that resolves to
  the frozen executable, and the arms fail as ordinary result rows rather than as
  an error. A `shiv` `.pyz` fixes that but inherits the tag of its native
  dependencies: one built on CPython 3.13 for macOS/arm64 fails on 3.12, on the
  same machine, with `ImportError: module 'harness' has no attribute 'cli'`.
  That is an artifact per OS per Python minor version, each failing
  unhelpfully. The wheel is `py3-none-any` — one file for every OS and every
  supported Python — and `pip` resolves the native dependencies per machine,
  which is the job `pip` is good at.
- **Metrics are unvalidated in field mode**, and 0 of 8 lint rules have a
  measured effect size. Both are printed on every artifact.
