"""The Z0 contamination gate.

Run first, before anything else. If a model can answer questions about this
catalogue with no access to the API, the domain leaked into pretraining and
every downstream number is meaningless — not weakened, meaningless, because the
thing being measured (does packaging help the model reach information it does
not have) no longer applies.

This is the one check that can void the entire experiment, so it fails loudly
and refuses to be waived.

Contract: archive/reference/experiment-design.md#contamination-gate
"""

from __future__ import annotations

from dataclasses import dataclass

#: Above this, the rig is contaminated. Not zero, because a lucky guess on a
#: yes/no-ish task is possible; low enough that systematic knowledge shows up.
Z0_THRESHOLD = 0.05


class ContaminationError(RuntimeError):
    """Z0 scored above threshold. Results are void, not merely suspect."""


@dataclass(frozen=True, slots=True)
class GateResult:
    score: float
    passed: bool
    answered: int
    total: int
    detail: str

    def render(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"Z0 gate: {verdict}  ({self.score:.1%} answered correctly with no "
            f"API access, {self.answered}/{self.total})\n  {self.detail}"
        )


def evaluate(grades) -> GateResult:
    """Score a Z0 arm.

    A correct refusal is the *expected* behaviour here: with no tools, the only
    honest answer to "what is the runtime of this episode" is that it cannot be
    determined. So refusals are not counted as successes — only a correct
    substantive answer counts against the gate, because only that indicates
    parametric knowledge of the domain.
    """
    from harness.engine.grader import Outcome

    scored = [g for g in grades
              if g.outcome not in (Outcome.TRUNCATED, Outcome.UNGRADED)]
    if not scored:
        return GateResult(0.0, False, 0, 0,
                          "no gradeable Z0 runs — the gate did not actually run")

    answered = sum(1 for g in scored if g.outcome is Outcome.PASS)
    score = answered / len(scored)
    passed = score <= Z0_THRESHOLD

    if passed:
        detail = (
            "The model cannot answer from parametric knowledge, which is the "
            "precondition for everything else."
        )
    else:
        detail = (
            f"{answered} of {len(scored)} tasks were answered correctly without "
            "any API access. The fictional domain is not contamination-free: "
            "either the generated names collide with something real, or the "
            "answers are guessable from the question. Fix the generator and "
            "re-seed — do not proceed."
        )
    return GateResult(score, passed, answered, len(scored), detail)


def require_pass(result: GateResult) -> None:
    """Hard gate. There is no override, deliberately.

    A flag to skip this would eventually get used under deadline, and the
    resulting numbers would look exactly like valid ones.
    """
    if not result.passed:
        raise ContaminationError(result.render())
