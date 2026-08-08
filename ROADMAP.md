# Roadmap

What is built, what is next, and what is deliberately not promised. Anything in
the third section **does not exist** — if a report, a doc or an agent tells you
otherwise, that is a bug.

## Now

The engine, both run modes, the static lint, the controlled rig and its answer
keys, the reporting stack, and the packaging and distribution path are built and
tested. The controlled matrix has run at 40 cores.

## Next

**Validate the gold-free metrics.** Field mode currently ships every metric
flagged `unvalidated` — computed and reported, but with no established
relationship to ground truth. The controlled rig is what flips those flags, one
metric at a time. Until then, the flag stays on the artifact.

**Back the lint rules with measurements.** All 8 rules are `heuristic` today.
Each carries a `justified_by` field pointing at the run that establishes its
effect size; the field is empty. Filling it is what turns the free tier from a
plausible checklist into a measured one.

**A thin local UI.** `harness ui` — pick a source (your API, or the built-in
mock with its knobs), lint it, configure a run against a live cost projection,
watch the transcripts arm by arm, read the report. Deliberately a wrapper over
the CLI, not a second implementation.

**Domain robustness.** A second theme for the rig. If arm ranking flips between
themes, the first matrix is a domain artifact — better to find that out here.

## Not scheduled

Designed for, so the interfaces are checked against them, but not built and not
promised.

| | What it would be |
|---|---|
| **D4 sandbox helpers** | A sandbox arm with pre-written helper functions, separating "can write code" from "can discover the surface" |
| **Operation ledger** | A per-operation report section — which endpoints agents get wrong, rather than which arms win |
| **TypeScript sandbox** | A runtime-comparability check against the literature, which uses TS. Stable ranking across runtimes is a finding; unstable is a bigger one |
| **MCP Tasks extension** | Async/long-running jobs. Poll-vs-callback is a packaging choice with real token cost that nobody has measured |
| **`llms.txt` / `AGENTS.md`** | Another `instructions` value; near-free once the seam exists |
| **Native provider tool-search** | A labelled sub-mode of retrieval, so "you benchmarked your own dispatcher" becomes a measured delta instead of a caveat |
| **Second provider** | A cheaper tier of the same provider comes first — the tier axis is worth more than the provider axis and costs less |

## Explicitly out of scope

- **MCP Apps / UI resources** — there is no human in the loop here.
- **Multi-agent delegation** — a different question with a different harness.
- **Ranking models, or ranking MCP servers.** The model is held constant inside
  any controlled comparison; results are stamped to it.

---

Each item above is a plugin or a renderer, not an engine change. That is the
seam the design exists to protect: the MCP spec moved mid-build on 2026-07-28,
and it will move again.
