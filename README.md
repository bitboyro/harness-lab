# harness-lab

**Does the way you package your API change how well an AI agent can use it?**

Same API, same tasks, same model — only the packaging changes: an MCP server, an
MCP server plus a written skill, docs and `curl`, a code-execution sandbox. The
harness runs an agent against each and reports which one it actually used
better, and what that cost.

```bash
harness lint --demo     # free, no API key, one second
```

## Why run commands, when your agent can do it for you?

Most of the work in a packaging study is not running the tool — it is deciding
what to test, writing tasks that a public model can't already answer, picking
arms your API actually supports, and refusing to overclaim the result. That is
work an agent is good at, so it ships as skills rather than as a manual.

```bash
harness init --agent claude     # or cursor, or both
```

Then, in Claude Code or Cursor:

> **help me test my API with harness**

Three skills are installed, and your agent picks whichever fits:

| Skill | Fires when | What it does |
|---|---|---|
| **harness-lab** | "what is this", "which command", "it broke" | Checks the install, picks the target, walks the cost ladder, and holds the line on what a result supports |
| **harness-field-pack** | "test *my* API" | Discovers your surface, drafts and fills a task pack, sets safety defaults, chooses arms and suite size |
| **harness-insights** | "give me a brief" | Turns a finished results directory into a narrative `insights.html` |

They know the parts that are easy to get wrong: never pooling incomparable
runs, that a lead under the MDE is a tie, that a probe cannot crown a winner,
and that spend needs your approval first. `harness init` also drops a
`packs/template.yaml` to start from.

Nothing here is agent-only. Every command below works on its own.

## Three steps, increasing in cost

| | Cost | What you learn |
|---|---|---|
| **`lint`** | $0 | Static agent-readiness findings on an OpenAPI doc or a live URL |
| **`run --probe`** | ~$1–20 | Whether an agent gets anywhere at all, on a handful of tasks |
| **`run`** | $50+ | Which packaging wins, with intervals you can defend |

Nothing spends without printing a projection and asking first.

## Point it at your own API

```bash
harness scaffold https://your-server/mcp -o packs/your-api.yaml   # drafts a pack
$EDITOR packs/your-api.yaml                                       # fill the TODOs
harness run --pack packs/your-api.yaml --probe                    # ~$1–20
harness report results/… --html report.html
```

`scaffold` writes one task stub per read operation, puts every operation it
won't exercise into `forbidden_calls`, and leaves every task **ungraded on
purpose** — a stub that asserted something plausible would look finished.

If you work with Claude Code or Cursor, `harness init --agent both` installs
skills that know this whole workflow, so your agent can do it with you.

## Watch it work

A real 9-run result ships with the tool, so there is something to open before
you spend anything:

```bash
harness report results/auth-smoke            # the scorecard, the winner, the ties
harness transcript results/auth-smoke/traces # what the agent actually did
```

And during a run of your own:

```bash
harness run … --stream --concurrency 1     # every message, live
harness transcript results/…/traces        # replay any run afterwards
```

## What it refuses to tell you

The useful part of this tool is mostly what it declines to say.

- It **never pools** results across models, MCP revisions, skill conditions, or
  controlled-vs-field runs. `harness compare` exits 3 rather than print a
  comparison that crosses one of those lines.
- A lead smaller than the run's own minimum detectable effect is reported as a
  **tie**, not a win — and "not detectable" is not "no difference".
- Confirmatory contrasts are **declared in code before any matrix runs**, so
  none can be added after seeing results.
- Cost is **decomposed, never totalled**, because a single number hides the
  mechanism the whole comparison is about.
- Runs killed by a dead key, a full disk or a rate limit are **excluded from
  every rate** and re-run, not counted as packaging failures.
- Every metric prints whether it is `validated-controlled`, `unvalidated`, or
  `heuristic`.

**Today, 0 of 8 lint rules have a measured effect size**, and the lint footer
says so on every run. They are hypotheses worth testing, not defects.

## Two modes

**Controlled** — a fictional media-catalog API generated in process from a seed,
with an answer key from the same source of truth. Correctness and harm are
properly gradeable, because the world and the answers come from the same place.

**Field** — any real REST API or live MCP server, described by a task pack.
Contamination is uncontrolled there, so every number is reported as lift over
`Z0`, the arm with no tools at all. That turns "the model already knows your
API" from a threat into a measurement.

Both run through one command and one execution path. The difference is a
*target*, not a second implementation.

## Install

Download one thing — `harness-lab-<version>.zip` — and unzip it. The wheel and
the installer are both inside, so nothing is fetched and no credentials are
needed:

```bash
python3 install.py --check     # what is missing, and what each thing blocks
python3 install.py             # installs the wheel next to it
harness doctor                 # same checks, any time after
```

Working from the repo instead, `python3 install.py --download` pulls the latest
release wheel straight from GitHub. No credentials and no extra tooling.

Two ways to run it and no third — `harness …` or `python3 -m harness …`.

Needs Python 3.11+, plus `curl` for the shell arms. Full options, and a warning
about the sandbox arms, in [docs/install.md](./docs/install.md).

> The **D arms execute model-written Python** in a temp directory with **no
> container isolation**. Run them somewhere you're comfortable with that;
> `--presets` without `D1`/`D2` avoids it.

## Docs

| | |
|---|---|
| [install.md](./docs/install.md) | Getting it running |
| [test-your-api-harness.md](./docs/test-your-api-harness.md) | Testing your own API |
| [design-your-test-run.md](./docs/design-your-test-run.md) | Deciding what the run measures — the task pack format |
| [controlled-rig.md](./docs/controlled-rig.md) | The built-in experiment |
| [reading-results.md](./docs/reading-results.md) | What the numbers mean |

[CHANGELOG](./CHANGELOG.md)

## Status

Pre-1.0. The engine, both run modes, the lint and the reporting are built and
tested; the controlled matrix has run at 40 cores. The lint rules are not yet
backed by measured effect sizes, and field metrics are unvalidated. Both facts
are printed on the artifacts rather than kept in a footnote.
