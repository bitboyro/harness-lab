# harness-lab

**Which kind of tooling do agents use best?**

Which packaging is most accurate? Which is cheapest? Which does the most damage?

harness-lab answers by **experiment**. 

Give an agent the same job several ways — an MCP server, an MCP server plus a written skill, docs and `curl`, a code sandbox, a code sandbox plus a skill and whatnot.
Same tasks, same model; only the packaging changes.

Then you can measure what the packaging is worth — tune it and repeat.

Each way of packaging is an **arm**:

| | | |
|---|---|---|
| `Z0` | No tools | control — what the model already knows without you |
| `A1` | MCP, all tools | every operation schema loaded upfront |
| `A2` | MCP, discovery | 3 meta-tools; schemas fetched on demand |
| `B1` | MCP, all tools + skill | `A1` plus a written skill |
| `C1` | Bash + docs | a written reference; the agent writes `curl` |
| `D1` | Code sandbox | operations as an importable module tree |

16 in all — `--presets` picks which ones run, and you can
[declare your own](./docs/controlled-rig.md#declaring-your-own-arm).

## Install

```bash
curl -fsSL -O https://raw.githubusercontent.com/bitboyro/harness-lab/main/install.py
python3 -m venv .venv && . .venv/bin/activate
python3 install.py --download
harness doctor                 # same checks, any time after
```

That fetches the latest release wheel from GitHub and installs it. 

The install itself needs no network, so this works airgapped. The zip is on the
[releases page](https://github.com/bitboyro/harness-lab/releases) too.

Needs Python 3.11+. Full options in [docs/install.md](./docs/install.md).

Then, to see it do something — free, no API key, one second:

```bash
harness lint --demo
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

Nothing here is agent-only. Every command below works on its own.

## Three steps, increasing in cost

| | Cost | What you learn |
|---|---|---|
| **`lint`** | $0 | Static agent-readiness findings on an OpenAPI doc or a live URL |
| **`run --probe`** | ~$1–20 | Whether an agent gets anywhere at all, on a handful of tasks |
| **`run`** | $50+ | Which packaging wins, with intervals you can defend |

Nothing spends without printing a projection and asking first.

> The **D arms execute model-written Python** in a temp directory with **no
> container isolation**. Run them somewhere you're comfortable with that;
> `--presets` without `D1`/`D2` avoids it.

## Point it at your own API or MCP server

```bash
harness scaffold https://your-server/mcp -o packs/your-api.yaml   # drafts a pack
$EDITOR packs/your-api.yaml                                       # fill the TODOs
harness run --pack packs/your-api.yaml --probe                    # ~$1–20
harness report results/… --html report.html
```

`scaffold` writes one task stub per read operation, puts every operation it
won't exercise into `forbidden_calls`, and leaves every task **ungraded on
purpose** — a stub that asserted something plausible would look finished.

Always keep `Z0`, the arm with no tools. On a real API it measures how much the
model already knows about yours, and every other arm is read as lift over it —
which turns contamination from a threat into a measurement.

If you work with Claude Code or Cursor, `harness init --agent both` installs
skills that know this whole workflow, so your agent can do it with you.

## Watch it work

A real 9-run result ships with the tool, so there is something to open before
you spend anything:

```bash
harness report results/auth-smoke            # the scorecard, the winner, the ties
harness transcript results/auth-smoke/traces # what the agent actually did
```

## The baseline experiment

A realistic media-catalog API with its own answer key, generated in process, so
correctness and harm are fully gradeable. Full detail in
[controlled-rig.md](./docs/controlled-rig.md).

## It won't oversell the result

The numbers are deliberately cautious. If one arm wins by less than the run is
precise enough to measure, that is reported as a **tie**, not a win — the gap is
noise, and dressing it up as a finding would be the easiest way to mislead you.
Results that aren't comparable are never averaged together, and every number
says whether it has been validated.

More in [reading-results.md](./docs/reading-results.md).

## Docs

| | |
|---|---|
| [install.md](./docs/install.md) | Getting it running |
| [test-your-api-harness.md](./docs/test-your-api-harness.md) | Testing your own API |
| [design-your-test-run.md](./docs/design-your-test-run.md) | Deciding what the run measures — the task pack format |
| [controlled-rig.md](./docs/controlled-rig.md) | The built-in experiment |
| [reading-results.md](./docs/reading-results.md) | What the numbers mean |

[CHANGELOG](./CHANGELOG.md)

## Feel free to contribute!

Issues and pull requests welcome.