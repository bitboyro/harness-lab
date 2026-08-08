---
name: harness-lab
description: >-
  Drive harness-lab end to end: check the install, pick the right command,
  choose a target, keep spend approved, and read the output honestly. Use when
  the user mentions harness, harness-lab, packaging benchmarks, MCP vs docs vs
  sandbox comparisons, asks what this tool does or which command to run, wants
  to test whether an agent can use an API, or hits an error running harness.
  Route to harness-field-pack for authoring a pack, harness-insights for a
  narrative brief.
---

# harness-lab (start here)

harness-lab answers one question: **does the way you package an API change how
well an agent can use it?** Same API, same tasks, same model — only the
packaging varies (MCP server, MCP + a written skill, docs + `curl`, a
code-execution sandbox, and a no-tools control).

You are the operator. The user should not have to learn the CLI.

## Two rules before anything else

1. **Runs cost real money.** Every spending command prints a projection and
   asks. Never pass `--yes` unless the user has approved that spend in this
   conversation. Quote the projection back to them before you run it.
2. **Never invent a number.** Everything you report comes from harness output —
   `lint`, `run`, `report`, `transcript`. If you did not see it printed, you do
   not know it.

## Workflow

Copy and track:

```
Harness progress:
- [ ] 1. `harness doctor` — is the machine ready
- [ ] 2. Pick the target: their API, or the built-in rig
- [ ] 3. `harness lint` — free, always do this first
- [ ] 4. Agree model + budget, then probe
- [ ] 5. Report, and say plainly what it does and does not support
```

## 1. Is it installed

```bash
harness doctor          # or: python3 -m harness doctor
```

Two ways to run it and no third: `harness …`, or `python3 -m harness …` when
the console script is not on PATH. If neither works, they have not installed
it — `python3 install.py --check` from the bundle says what is missing and what
each missing thing blocks.

`doctor` exits non-zero only when something *required* is absent. A missing
`OPENAI_API_KEY` is a warning, not a failure: `lint` does not need one.

## 2. Which target

| The user has | Target | Route |
|---|---|---|
| Their own REST API or MCP server | **field** | `harness scaffold` → **harness-field-pack** skill |
| Nothing yet, wants to see it work | **controlled rig** | `--smoke`, then the matrix |
| A results directory already | — | **harness-insights** skill |

The controlled rig is a fictional media-catalog API generated in process from a
seed, with an answer key from the same source of truth. That is what makes
correctness and harm gradeable there. Field mode has no answer key unless the
user's pack supplies one, so it reports **lift over Z0** — the arm with no tools
at all — which turns "the model already knows your API" from a threat into a
measurement.

## 3. The ladder — never skip a rung

| Rung | Command | Cost | What it buys |
|---|---|---|---|
| **Lint** | `harness lint <spec-or-url>` | $0 | Static agent-readiness findings |
| **Smoke** | `harness run --out /tmp/s --id s --smoke --yes` | ~$0.05 | Proves the pipeline, not a result |
| **Probe** | `harness run --pack p.yaml --probe` | ~$1–20 | Does an agent get anywhere at all |
| **Matrix** | `harness run --out results/<id> --id <id>` | $50+ | A defensible winner |

`harness lint --demo` lints the built-in API — free, no key, one second. It is
the right first thing to show anyone.

Never crown a winner from a probe. One repeat over a handful of tasks cannot
clear the run's own minimum detectable effect, and the report will say so.

## 4. Commands

| Command | Cost | What it does |
|---|---|---|
| `harness doctor` | $0 | Environment check; says what each gap blocks |
| `harness lint <spec\|url>` | $0 | T1 scorecard. `--demo` for the built-in API |
| `harness scaffold <url> -o packs/x.yaml` | $0 | Draft a pack from a live MCP server or OpenAPI doc |
| `harness init --agent both` | $0 | Install these skills into a project |
| `harness rig --cores N --out rig` | $0 | Size a matrix; prints its power table |
| `harness plan <plan.yaml>` | $0 | Cost projection and approval gate |
| `harness run …` | $$ | The only run command — rig or pack, same path |
| `harness progress DIR` | $0 | Read a run in flight from a second terminal |
| `harness report DIR --html r.html` | $0 | Render stored results; re-runs nothing |
| `harness compare DIR DIR…` | $0 | N-run diff; refuses to pool incomparable runs |
| `harness transcript <trace>` | $0 | Replay a run: messages, calls, arguments, results |

There is **no `harness probe`**. Field mode is `harness run --pack`, the same
execution path as the matrix — so it gets the ledger, `--concurrency`,
`--resume`, `report`, `compare` and `progress` too.

To let the user *watch*: `--stream --concurrency 1`. Above concurrency 1, turns
from different runs interleave and the stream is unreadable.

## 5. When something fails

| Symptom | Meaning |
|---|---|
| Exit **3** | `REFUSING TO POOL` — you asked it to compare runs that are not comparable. This is correct behaviour, not a bug. Do not work around it |
| Exit **40** | Setup problem: bad model name, unreadable pack, dead key, full disk. Nothing ran and nothing was charged |
| An arm sitting at ~0% | Read the trace before believing it. A zero is far more often broken wiring than a finding |
| `infra-error` rows | A run killed by the machine, not by the packaging. Excluded from every rate; `--resume` re-runs them |

A matrix that dies leaves everything it finished — the ledger is append-only.
`--resume` picks up where it stopped. Never restart from scratch to "be safe";
that spends the money twice.

## 6. Reporting back — what you may and may not claim

The tool's refusals are its most valuable feature. Preserve them in your summary:

- A lead smaller than the run's own **MDE is a tie**, not a win. And "not
  detectable at this n" is not "no difference".
- **Never pool** across models, MCP revisions, skill conditions, or
  controlled-vs-field. If `compare` exits 3, report that as the finding.
- **Cost decomposes, never totals** — static context, per-call overhead, session
  setup, payload, sandbox seconds, round trips. One number hides the mechanism
  the whole comparison is about. Compare dollars across providers, never tokens.
- Results are **stamped to one model version**. Not "APIs in general".
- Every metric carries `validated-controlled`, `unvalidated` or `heuristic`, and
  field metrics are `unvalidated`. Say so.
- **0 of 8 lint rules currently have a measured effect size.** Lint findings are
  hypotheses worth testing, not defects. Never present one as a proven cost.

If the user asks you to drop a caveat to make the result look cleaner, say what
the caveat protects and let them decide. Do not quietly remove it.

## Handing off

- Authoring a pack for a real API, choosing arms, safety, suite size →
  **harness-field-pack**
- Turning a finished results directory into a narrative `insights.html` →
  **harness-insights**

## Docs on disk

`docs/install.md`, `docs/test-your-api-harness.md`, `docs/design-your-test-run.md`,
`docs/controlled-rig.md`, `docs/reading-results.md`. Read the relevant one
before changing behaviour it describes; quote it rather than paraphrasing from
memory.
