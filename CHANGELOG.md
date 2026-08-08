# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [semver](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-08-08

First release.

### Commands

| | |
|---|---|
| `harness lint` | Static agent-readiness scorecard over an OpenAPI doc or a live URL. Free, no API key. `--demo` lints the built-in API |
| `harness run` | One command and one path for both the controlled matrix and a live target. `--pack` selects a real API, `--probe` is a first-contact profile, `--smoke` proves the pipeline for about $0.05 |
| `harness scaffold` | Drafts a task pack from a live MCP server or an OpenAPI doc |
| `harness init` | Installs the agent skills into a project (`--agent claude\|cursor\|both`) |
| `harness report` | Renders stored results as text, HTML, charts or CSV. Re-runs nothing |
| `harness compare` | N-run diff. Exits 3 rather than pool runs that are not comparable |
| `harness transcript` | Replays a stored run: every message, call, argument and result |
| `harness progress` | Reads a run in flight from a second terminal |
| `harness plan` | Cost projection and approval gate for a declared matrix |
| `harness rig` | Sizes the controlled rig and prints its power table |
| `harness doctor` | Checks the machine, and says what each missing piece blocks |

`--stream` prints the exchange live during a run. `python -m harness` works
wherever the `harness` script does.

### Agent skills

`harness init` installs three, for Claude Code and Cursor:

- **harness-lab** — install check, target choice, the cost ladder, and what a
  result does and does not support
- **harness-field-pack** — surface discovery, pack authoring, safety, arms
- **harness-insights** — a finished run to a narrative `insights.html`

### Install

A wheel (`py3-none-any` — one file for every OS and every supported Python) and
`install.py`, which runs on any Python 3 so an interpreter too old to run
harness gets an explanation instead of a `SyntaxError`.

### Known limits

- **0 of 8 lint rules have a measured effect size.** They are hypotheses, and
  every scorecard says so.
- **Field metrics are unvalidated** against the controlled rig. Every metric
  carries `validated-controlled`, `unvalidated` or `heuristic`, printed on the
  artifact.
- Only the `openai` provider is wired.
- The `D` arms execute model-written Python with no container isolation.

[0.1.0]: https://github.com/bitboyro/harness-lab/releases/tag/v0.1.0
