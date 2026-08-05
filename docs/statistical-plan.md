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

Phase 1 as specced: 15 cores × 5 terminals × 6 arms × 3 repeats = 1,350 runs.

Within-core paired contrasts, α = 0.0083 (Holm's first step at six tests),
power = 0.80, and an intra-core correlation assumed at ρ ≈ 0.3 (conservative;
re-estimated from Phase 0 and this plan updated **before** Phase 1 if it differs
materially):

| Comparison | n per arm | MDE (percentage points) |
|---|---|---|
| Arm vs arm, pooled across classes | 225 | ≈ 9 pp |
| Arm vs arm, within one task class | 45 | ≈ 20 pp |
| Interaction (arm × class) | — | ≈ 25 pp difference-in-differences |

**Read this honestly: Phase 1 is powered for main effects and underpowered for
the interaction** — which is the headline result. Two consequences, both decided
now rather than after seeing the data:

1. If the interaction is the result worth having, cores must increase. **25 cores
   brings the interaction MDE to roughly 15 pp** at the same repeat count. At
   luna's rates the whole matrix is on the order of $10–20, so cores are cheap
   and there is no budget reason to stay underpowered.
2. If Phase 1 runs at 15 cores anyway, the interaction is reported **with its
   confidence interval and an explicit underpowered caveat**, never as a null.

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
