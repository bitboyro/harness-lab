# Reading the results

```bash
harness report results/matrix-40
harness report results/matrix-40 --html report.html --charts charts/
harness report results/matrix-40 --glossary        # every term, defined
```

Renderers never recompute. Text, HTML and CSV all consume one analysis object,
so they cannot disagree with each other.

## The arms

Every report opens by naming what was actually compared, derived from each run's
recorded axis assignment rather than from a hand-written label — so a chart can
never be captioned with something the run wasn't.

| | Packaging |
|---|---|
| `A1` | MCP, every operation schema loaded upfront |
| `A2` | MCP, search/describe/invoke triad — schemas on demand |
| `B1` `B2` | A1/A2 plus a generated skill. `-auth` twins use the authored one |
| `C1` `C2` | A written reference plus `curl` in a shell |
| `D1` `D2` | A code sandbox over a generated module tree |
| `E1` | Top-k tool retrieval |
| `M1` | Server asks before destructive operations |
| `Z0` `Z1` | **Controls**, marked `†` — see below |

**Controls are not packaging.** `Z0` has no tools; `Z1` is handed the answers.
Neither is shippable, so neither is ever a candidate to win. `Z0` is the floor
every other arm is measured against; `Z1` is the ceiling.

## The numbers

**Success** — tasks got right, counting correct refusals of unanswerable tasks.

**Lift** — success minus Z0's. On the controlled rig Z0 must score ≈0 or the
testbed is contaminated and everything is void. In field mode Z0 is not a gate
but a measurement: how much the model already knew about your API.

**Abstention** — of the tasks with *no* valid answer, the share correctly
declined. Reported separately because it is the failure that matters most and
the one a success rate hides.

**Cost** — decomposed, never totalled: static context, per-call overhead,
session setup, payload, sandbox seconds, round trips. A single number would hide
the mechanism the whole study is about. Compare dollars across providers, never
tokens — the tokenizers differ.

**Harm** — runs that destroyed data or attempted a forbidden call. On the rig
this is graded from a state diff; on a real API state cannot be diffed, so an
*attempted* forbidden call is the entire signal.

## How the winner is chosen

Five dimensions, each rescaled 0–1 across the packaging arms, oriented so higher
is better, then weighted:

| Dimension | Weight |
|---|---|
| success | **0.35** |
| harm | **0.25** |
| abstention | **0.15** |
| cost | **0.15** |
| time | **0.10** |

Safety (0.40 combined) outweighs thrift (0.25), so an arm cannot buy the top
spot by being cheap and dangerous. Override with `--weights success=.5,cost=.5`;
unnamed dimensions are **dropped, not defaulted**, so `--weights harm=1` means
harm alone.

Abstention is weighted separately because only ~15% of tasks are unanswerable —
an arm that fabricates an answer on *every one of them* loses at most 15 points
of success, about 0.05 of composite. Far too little for that failure.

**The score is a decision aid, not evidence.** A composite always produces a
ranking, including one built entirely from noise. So the verdict prints whether
the leader's lead exceeds the run's MDE:

```
On success, B1 and D2 are TIED: 9.7 pp apart, below the 40.2 pp this
run can detect. The score gap is made of the other dimensions, not of
accuracy.
```

It also refuses to pick when arms tie exactly, names any dimension that
separated nothing, and says so when the winner harms or fabricates more than its
runner-up. Read the score to shortlist; read the interval before acting.

## What the report refuses to do

These are the load-bearing parts. They are why a number here is worth more than
a number from a spreadsheet.

- **It will not pool** across model, MCP revision, skill condition, or report
  class. `harness compare` prints `REFUSING TO POOL` and exits 3.
- **It will not call a sub-MDE gap a finding.** "Not detectable" is printed, and
  it is not the same as "no difference".
- **It corrects for multiple comparisons.** Confirmatory contrasts are declared
  in code before any matrix runs and Holm-corrected; exploratory ones are
  labelled and uncorrected, and never promoted afterwards.
- **It excludes infra errors from every rate.** A run killed by a full disk
  measured nothing about packaging.
- **It prints every metric's validation flag** — `validated-controlled`,
  `unvalidated`, or `heuristic`. Field mode ships unvalidated metrics; that is
  acceptable only because it is stated on the artifact.

## Operation ledger

⚠ AMENDED — section rewrite: clearer copy; controlled gold augmented with
terminal writes; stumble ranked by rate × volume; families pluralized;
per-arm cards and skill/discovery contrast pairs; HTML charts/tables.

After the mechanism metrics, the report names **which parts of the API** agents
lean on and misuse — so you know what to document, hide, or redesign. Built at
report time from traces; nothing in the agent loop changes. This is **not** how
you pick a packaging winner (that is the scorecard above).

Resolution is by packaging *axes* (transport / discovery / invocation), never by
arm name — a custom arm that behaves like A1 is scored like A1.

On the controlled rig, stored `gold_call_sequence` is the **navigation** path;
writes are graded on final state. The ledger **adds** the terminal ops each
task class needs (`patch_episode`, `archive_episode`, …) so “off-path” means
wandered away from the solution, not “called the write the grade requires.”

**Blocks:**

| Block | What it shows |
|---|---|
| **A. Over-touch** | Called more than the gold path expects — document or hide candidates. Without gold, raw usage only. |
| **B. Stumble by kind** | Off-path, call-error, and forbidden ranked separately by rate × volume. |
| **C. Families** | Resource families (episodes, assets, …). |
| **D. Per-arm cards** | For each packaging: lean-on endpoint, top spend, top stumble. |
| **E. Skill contrasts** | Fixed pairs (e.g. A1→B1-auth, D1→D2-auth): did the skill change which ops are misused? Descriptive only. |

No gold ⇒ off-path / over-touch stay **unavailable**, not zero. Shell/code arms
note approximate transcript parsing in the footnotes. Volume is not blame;
HTTP-clean can still harm; unanswerable thrash is abstention, not an outage.

## Reading a single run

```bash
harness transcript results/matrix-40/traces --limit 3
harness transcript results/matrix-40/traces/some-run.json.gz
```

Every message sent to the model, every tool call with its arguments, every
result, timings and tokens per turn. Blocked calls are marked as harm;
truncation is marked as a budget failure rather than a wrong answer.

**Read traces before believing any arm at ~0%.** A zero is far more often a
wiring problem than a finding.

## Further

- `harness report DIR --glossary` — every metric's definition and its
  validation status, printed next to your own numbers
- `harness rig --cores N` — the power table for a matrix that size, so you can
  see which contrasts it could resolve before you pay for it
- `harness compare A B` — what differed in the setup, and what that changed
