# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Note: the parent workspace `bitboy.ro/.claude/CLAUDE.md` describes a Java/Spring platform. **None of it applies here.** `harness-lab` is a standalone Python research project with no relationship to those services beyond sharing a directory.

## What this is

A research harness that measures how the **packaging** of an API — MCP server, MCP + skill, docs + curl, code-execution sandbox — affects an LLM agent's ability to use it, holding the API, task set and model constant. It runs in two modes:

- **Controlled** — against a fictional, contamination-free media-catalog API generated in-process (`harness.experiment`). Correctness and harm are gradeable here, because the answer key comes from the same seeded world.
- **Field** — against any real API or live MCP server via a task pack. Gold-free metrics only, unless the pack supplies answers.

Runs cost real provider money. Every command that spends prints a projection and asks first.

## Setup and commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,openai]'
```

Credentials live in `.env` at the repo root (gitignored; `.env.example` is the template). Nothing needs exporting — `main()` loads `.env` and prints which names it found. Use `.venv/bin/harness` or activate the venv.

```bash
.venv/bin/python -m pytest -q                       # full suite, ~11s, no network, no key
.venv/bin/python -m pytest tests/test_stats.py -q   # one file
.venv/bin/python -m pytest -k "pooling" -q          # one test by name
```

There is no linter or formatter configured; don't add one uninvited.

The CLI (`harness.cli`, entry point `harness`):

| Command | Cost | What it does |
|---|---|---|
| `harness lint <spec>` | $0 | T1 static agent-readiness scorecard over an OpenAPI doc |
| `harness rig --cores N --out rig` | $0 | Inspect/size the controlled rig and print its power table (not a prerequisite for `run`) |
| `harness scaffold <url> -o P` | $0 | Draft a task pack from a live MCP server or an OpenAPI doc |
| `harness init [--agent …]` | $0 | Install the agent skills into a project |
| `harness run --pack P --probe` | ~$5–20 | T2: first contact with a real target, gold-free metrics |
| `harness run --out DIR --id NAME` | $$ | The controlled matrix; persists ledger + traces + manifest |
| `harness transcript <trace>` | $0 | Replay one run: messages, calls with arguments, results |
| `harness progress DIR` | $0 | Read a run in flight from a second terminal |
| `harness report DIR [--html/--charts/--csv/--glossary]` | $0 | Render stored results; re-runs nothing |
| `harness compare DIR DIR…` | $0 | N-run diff: what differed in the setup, and what it changed |
| `harness plan <plan.yaml> [--approve]` | $0 | Cost projection and approval gate for a declared matrix |

A smoke run that exercises the whole pipeline cheaply:

```bash
harness run --out /tmp/smoke --id smoke --smoke --yes
```

`docs/controlled-rig.md` is the operator manual — the recommended 40-core matrix, resume, and what a broken run looks like. `docs/test-your-api-harness.md` covers field mode, and `docs/reading-results.md` covers how the winner is scored.

## Architecture

Two packages under `src/harness/`, and the boundary between them is the most important thing in the repo.

```
engine/       API-agnostic core — the reusable tool
experiment/   the fictional catalog API, seeder, answer keys, grader
```

**`engine` must never import `experiment`.** The rig is a *consumer* of the engine through the same task-pack interface a field user gets. If the rig needs an engine feature no field user could reach, that is a design bug. `tests/test_layering.py` enforces this by AST-walking every engine module, and also forbids vendor SDK imports (`openai`, `anthropic`, …) in the engine — providers are adapters (`engine/providers/`), never core.

### Engine, roughly in dataflow order

- `axes.py` — the orthogonal variant space (`transport`, `discovery`, `invocation`, `instructions`, `confirmation`, plus affordance and run axes). A `Variant` is a **complete** assignment; an unset axis is a `ConfigError`, not a default. `preset("A1", **base)` expands a preset name into one. Arm display names are *derived* from the axis assignment (`short_name`/`describe`) so a chart can never be labelled with something the run wasn't.
- `packaging.py` — the `PackagingMethod` plugin protocol (`materialize` / `executor` / `account`) plus `Materials`, `Provenance`, `CostBreakdown`. **Adding a packaging method is a new file in `methods.py`, never an engine change** — that seam exists because the MCP spec moved mid-design and will again.
- `methods.py` — the plugins: `EagerAllMcp`, `MetaToolsMcp`, `CodeFsMcp`, `DocsShell`, `RetrievalMcp`, `GoldPreExecuted`, `NoTools`.
- `generate.py` — one OpenAPI spec → tool defs, meta-tools, skill markdown, curl reference, module tree. This is validity control V1: all arm materials are mechanically generated from a single source, except the deliberately-exempt authored skill.
- `loop.py` / `executors.py` — the agent loop is owned by the harness, never delegated to a vendor agent framework (that would inject an uncontrolled harness). Executors: MCP tool-call (both revisions), shell+curl subprocess, Python code sandbox, pre-executed (Z1), null (Z0).
- `mcp/` — dual-revision client (`2026-07-28` and `legacy`) plus HTTP transport.
- `trace.py` / `compute.py` / `metrics.py` — full trajectory capture, then gold-free metrics computed from it.
- `results.py` — `ResultStore` over `results.jsonl` (append-only, one row per run) and `manifest.json` (the run-level config snapshot, written before the first cell).
- `analysis.py` / `stats.py` / `winner.py` — `Report` is the single analysis object every renderer consumes. `stats.CONFIRMATORY` holds the pre-registered contrasts, declared in code so none can be added after seeing results.
- `reporting.py`, `html.py`, `svg.py`, `comparison*.py`, `glossary.py` — renderers. All read `Report`; none recompute.
- `lint.py` / `rules.py` / `justify.py` — T1 rules, each carrying `justified_by`. A rule with no justifying run renders as `heuristic`, not `measured`.
- `infra.py` — the error taxonomy separating "the machine broke" from "the arm failed".

### Experiment

`domain.py` (seeded world) → `openapi.py` (spec, padded to `surface_size` with distractors) → `server.py`/`http.py` (the API, in-process and over an ephemeral port) → `mcp_surface.py` → `rig.py` (`RigInstance`: one freshly seeded catalog + every surface an arm might need, per run) → `tasks.py` (matched-pair task packs with answer keys) → `grader` path in `engine/grader.py`. `gate.py` is the Z0 contamination gate; `power.py` sizes a matrix against a target MDE.

## Invariants that are easy to break

These are load-bearing for the research claims, not style preferences. Most have a test behind them; all have a rationale in `archive/reference/decisions.md`.

- **Isolation is per run.** Each run gets its own seeded API instance and ephemeral port, so mutating tasks parallelize safely and nothing contaminates the next cell.
- **Never pool** across `model`, `mcp_revision`, skill condition (generated vs. authored), or report class (controlled vs. field). `harness compare` prints `REFUSING TO POOL` and exits 3 when a boundary breaks — that exit code is what makes `harness compare a b && publish` refuse.
- **Cost decomposes, never totals**: `static_tokens`, `per_call_overhead_tokens`, `session_setup_tokens`, `payload_tokens`, `sandbox_seconds`, `round_trips`. A single number hides the mechanism the study is about. Compare dollars across providers, never tokens.
- **Every metric carries a `validation` flag** (`validated-controlled` / `unvalidated` / `heuristic`), printed in every report footer. Field mode ships unvalidated metrics; that is acceptable only because it is stated on the artifact.
- **Infra failures are not results.** A run killed by a full disk, dead key or 429 is graded `infra-error` with an `error_kind`, excluded from every rate, and **re-run by `--resume` rather than skipped**. Classification never reads response text — only errno, typed provider codes and transport status. On `disk`/`auth`/`billing` the matrix aborts immediately with exit code 40.
- **The ledger is append-only**, written per run under a write lock, so a matrix that dies leaves what it finished. Re-running a voided cell appends a new row; readers take the newest per `(arm, task, repeat)`.
- **`reasoning_effort` is always sent explicitly.** An unset provider default silently benchmarks effort levels instead of packaging (V3).
- **Doc budget is measured, not equalized.** Static context is a real causal property of a packaging choice; padding to parity would measure artificially padded docs (V2 dropped, see spec §8).
- **Authored materials require an `authored_commit`** in `Provenance` — that commit is the pre-registration proving the skill predates the results (V9). `Provenance.__post_init__` raises without it.
- **No LLM judge for correctness.** Programmatic grading only; writes graded on final server state, never on the transcript.
- **Nothing spends without printing a projection and confirming** (`--yes` to skip), and `harness run` refuses to start if free disk can't cover projected traces plus 5 GB of swap headroom.

## Docs are contracts, not notes

Docs are the reasoning trail, and code comments cite them by ID (`L1`, `F4`, `G6`, `V9`, `API-8`, `RQ3`). Read the relevant one before changing behaviour it describes.

**`docs/` ships. `archive/` does not.** That split is a distribution decision, not a statement about which is current — the reference contracts under `archive/reference/` are as live as anything in the repo, they are just not published.

> **The remote is public.** `archive/` is gitignored, which keeps it out of the
> working tree of a commit — it does **not** keep it out of history. Those paths
> were once committed and then removed; the commits were rewritten before any
> push so no object on `main` contains them. Two rules follow:
>
> - **Never `git add -f` anything under `archive/`.** The gitignore is the only
>   thing standing between an internal document and a public repository.
> - **Never push `p0-contracts` or `archive/p0-contracts`.** Both branches carry
>   the full research log in their trees, including everything under `archive/`.
>   They exist as local backups. Same for the `archive/*` tags.

| File | Ships | Role |
|---|---|---|
| `docs/install.md`, `test-your-api-harness.md`, `controlled-rig.md`, `reading-results.md` | yes | The four reader-facing guides |
| `docs/design-your-test-run.md` | yes | Frozen contract: the interop format that makes bring-your-own-API possible |
| `archive/reference/experiment-design.md` | no | Research requirements: RQs, the test API, metrics, validity controls |
| `archive/reference/packaging-axes.md` | no | Frozen contract: axes, plugin interface, preset table |
| `archive/reference/statistics.md` | no | Model, power/MDE, confirmatory vs. exploratory split — written before any matrix ran |
| `archive/reference/decisions.md` | no | **The reasoning.** Stable IDs (F/G/O) that code cites; treat them as an API |
| `archive/ROADMAP.md` | no | Internal planning |

Code cites these by **slug anchor**, not section number — a number drifts
silently, a renamed heading fails `tests/test_docs.py`. That test checks the
`archive/reference/` citations in full when the directory is present and skips
when it is not, so a checkout without the research trail still passes.
Genuinely superseded records (`plan.md`, `plan-review.md`, the proposals) sit
beside them, and on the `archive/p0-contracts` branch.

**Nothing under `docs/` may link into `archive/`** — a shipped doc must not
point at a file the reader does not have. Cite the decision ID in prose
instead.

When behaviour changes, amend the doc in the same commit — with an `⚠ AMENDED` marker rather than a silent rewrite, so a reader meets the argument instead of the omission.

## Repo conventions

- **Comments explain why, not what.** The existing code is dense with rationale — a paragraph on why a lock is held, why an exit code is distinct, why a digest hashes prompts and not ids. Match that register; a comment restating the line below it is noise here.
- Renderers never recompute; they take a `Report`. New output formats go alongside `comparison_html.py` / `comparison_csv.py`, reading the same object.
- `results/` and `traces/` are gitignored, except that `results.jsonl` and `manifest.json` for published runs **are** committed — those are what a reader needs to check a claim. Full traces are published separately as a corpus.
- `src/harness/experiment/skills/catalog.md` is the rig's authored skill for the `-auth` arms — a fixture of the experiment, not a user-facing feature. Editing it after results exist invalidates the V9 pre-registration.
- `src/harness/agent_skills/` is the canonical source of the three client-facing workflow skills: `harness-lab` (the router — install, command ladder, what a result supports), `harness-field-pack` (surface → pack → run), `harness-insights` (results → brief). They ship inside the wheel; `harness init --agent claude|cursor|both` copies every directory it finds there, so a new skill needs no CLI change. Do not check a second copy into `.cursor/` — it drifts.
- **`skills/<api>.md` at the cwd stays a user convention**: it is where somebody testing their own API puts their authored skill.
