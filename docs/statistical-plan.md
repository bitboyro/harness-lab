# Statistical Analysis Plan

**Status:** Pre-registered — committed before any matrix run
**Date:** 2026-08-05
**Decision:** [G8](./decisions.md#g8--statistical-plan-written-with-the-rig)

Written in the same commit as the controlled rig, before any results exist. That
timing is the point: declared afterwards, every result is confirmatory and every
correction is optional.

"≥3 repeats" is not an analysis plan. With 6+ arms × 5 task classes × 4 strata, a
ranking flip driven purely by noise is near-certain, and without a stated model
there is no way to tell one from a result.

---

## 1. What varies, and what that implies

| Level | Unit | Notes |
|---|---|---|
| Run | one (task × arm × repeat) | The observation |
| Task | one terminal on a core | Five terminals per core |
| Core | a navigation problem | Tasks within a core share every difficulty dimension (V7) |
| Arm | a packaging variant | Compared **within** core |

Two consequences follow, and both are easy to get wrong:

- **Runs are not independent.** Tasks nest in cores; a core that happens to be
  hard makes all five of its terminals hard. Treating runs as independent
  overstates precision — the standard errors would be too small and everything
  would look significant.
- **Repeats at fixed temperature measure sampling noise only.** They say nothing
  about variance across *task instances*. Wanting a tighter estimate of the arm
  effect means **more cores**, not more repeats. Repeats buy precision on one
  task; cores buy generalisation.

---

## 2. Primary model

Mixed-effects logistic regression on run-level success:

```
success ~ arm + task_class + arm:task_class + (1 | core)
```

- `arm` — fixed effect, the quantity of interest
- `task_class` — fixed effect (R / W-safe / W-lossy / W-irrev / RW-fan)
- `arm:task_class` — the interaction **is** RQ4; a significant term here is the
  headline result (P5), because it means no single arm ranking exists
- `(1 | core)` — random intercept, absorbing per-core difficulty

Fitted with `statsmodels` (or `lme4` via `rpy2` if convergence proves awkward).
Contrasts are **paired within core**: an arm is only ever compared against
another arm on the same core, never across cores.

For continuous outcomes (turns, cost per success, static context) the same
structure with a linear link. Cost is analysed in **dollars**, never tokens —
tokenisers differ across providers, so token counts are not comparable (§5.6).

---

## 3. Confirmatory vs. exploratory

Declared here, enforced by the run planner, which refuses a publishable matrix
with no `confirmatory` block.

### Confirmatory — corrected, pre-registered

| # | Contrast | Hypothesis |
|---|---|---|
| C1 | B1 vs A1 | P4 — a skill layer helps on an identical MCP surface (RQ1) |
| C2 | B2 vs A2 | P4 — the same, under discovery |
| C3 | A2 vs A1 across surface sizes | P3 — per-operation degrades as the surface grows (RQ2) |
| C4 | C1/C2 vs A1/B1 on harm per 100 tasks | P2 — freehand curl is more destructive (RQ3) |
| C5 | arm × task_class interaction | P5 — arm ranking reverses between read and write (RQ4) |
| C6 | `error_detail` main effect vs `instructions` main effect | P6 — fixing errors beats shipping a skill (G4) |

Multiple comparisons: **Holm–Bonferroni across the six confirmatory tests.**
Holm rather than plain Bonferroni because the tests are correlated and Bonferroni
would be needlessly conservative; not FDR, because with six tests a
family-wise-error guarantee is affordable and easier to defend.

### Exploratory — labelled, uncorrected

Everything else: D-arm comparisons, `mcp_revision` cost effects (P7), MRTR harm
(P8), the authored-vs-generated skill gap (P9), retrieval Recall@k. Reported as
exploratory in every table. **An exploratory result may generate a hypothesis; it
may not support a claim.**

Promotion from exploratory to confirmatory requires a fresh pre-registration and
new data. Re-analysing the same runs under a new label is the failure this split
exists to prevent.

---

## 4. Power and the minimum detectable effect

> **Corrected 2026-08-06.** The first version of this section carried MDEs of
> ≈9 / ≈20 / ≈25 pp. Those were too optimistic: they treated all 225 runs per arm
> as independent replicates of the difference, which ignores that the size of an
> arm effect varies from core to core. That heterogeneity does not shrink by
> adding repeats. The figures below come from
> `harness.experiment.power`, which is executable and testable, and they are
> the ones that govern.

**The core is the unit of analysis, not the run.** Each core yields one paired
difference between two arms, and the test is over those differences. Two terms
drive the variance, and they behave differently:

- **Measurement noise** — shrinks by averaging more observations inside a core,
  so repeats help here.
- **Effect heterogeneity** — how much the arm gap itself differs between cores.
  This divides by the number of cores and by nothing else. **No number of
  repeats touches it.**

That is the formal version of "more cores, not more repeats", and it is why the
two are not interchangeable.

Assumptions: α = 0.0083 (Holm's first step at six tests), power = 0.80,
ρ ≈ 0.3 within core, effect heterogeneity 0.01, worst-case baseline p = 0.5.
ρ is re-estimated from Phase 0 and this section updated **before** the main
matrix if it differs materially.

| Cores | Main effect | Within class | Interaction |
|---|---|---|---|
| 15 (as originally specced) | 16.4 pp | 32.0 pp | 23.2 pp |
| 25 | 12.7 pp | 24.8 pp | 18.0 pp |
| **40** | 10.0 pp | 19.6 pp | **14.2 pp** |
| 60 | 8.2 pp | 16.0 pp | 11.6 pp |

To reach a 15 pp detectable effect: **18 cores** for main effects, **36 cores**
for the interaction, **69 cores** for within-class comparisons.

**Phase 1 at 15 cores is underpowered for everything except main effects**, and
the interaction — the headline result (P5, RQ4) — needs roughly **40 cores**, not
the 25 previously claimed. Decided now rather than after seeing data:

1. **Phase 1 runs at 40 cores.** At luna's rates that is single-digit dollars, so
   there is no budget argument for staying underpowered. Cores are the cheap
   axis; being unable to answer the study's own question is the expensive one.
2. **Within-class contrasts stay underpowered** at any plausible size (69 cores
   for 15 pp, and that is per class). They are therefore **exploratory by
   construction** and are not on the confirmatory list.
3. Any contrast that does run underpowered is reported **with its confidence
   interval and an explicit caveat**, never as a null.

Demonstrating the point, at 25 cores: going from 3 to 30 repeats — ten times the
runs and ten times the cost — moves the interaction MDE only from 18.0 pp to
10.9 pp, while going to 81 cores at 3 repeats reaches 10 pp. Repeats are the
expensive way to buy the wrong thing.

Absence of evidence is not evidence of absence, and an underpowered null will be
labelled as such.

---

## 5. Stopping and exclusions

Declared in advance so neither can be used to steer a result.

- **Fixed n.** No optional stopping. The matrix runs to completion; peeking is
  not a basis for stopping early.
- **Truncated runs** (hit `max_turns`) are excluded from success-rate models and
  **reported separately as a truncation rate**. They are a budget failure, not a
  wrong answer, and pooling them would blame the model for a harness setting.
- **Harness errors** (provider 5xx, transport failure) are excluded and reported.
  If exclusions exceed 5% of any arm, that arm's results are held: a systematic
  failure to run is itself a finding about the packaging.
- **No post-hoc exclusion of tasks.** A task that every arm fails is informative;
  removing it because it "seems broken" after seeing results is not available.

---

## 6. What gets published regardless

- Disconfirmed predictions, stated as such. P1–P9 are on record; the ones that
  fail get reported with the same prominence as the ones that hold.
- The Z0 score, always, alongside every result.
- Exclusion counts per arm.
- The full trace corpus, so any of this can be recomputed by someone who
  disagrees with the model above.

---

## 7. Threats this plan does not fix

Stated plainly, because a plan that claims to solve everything is not credible.

- **Single model.** Phase 1 is one model; effects may not transfer. That is what
  Phase 3 replication and the tier axis are for, and until they run, every claim
  is scoped to one model version (V8).
- **Generated-skill ceiling.** A null on RQ1 under `skill-generated` alone is
  uninterpretable, which is why V9 requires the authored condition. If only the
  generated condition runs, RQ1 is not answered.
- **Domain artifact.** One theme. If the arm ranking flips under the fleet theme,
  Phase 1 describes media catalogues rather than APIs — which is why the second
  theme exists and why it must run before any general claim.
- **Our own dispatcher.** The meta-tools triad is hand-rolled; the labelled
  native-tool-search variant measures how much of the discovery result is ours.
