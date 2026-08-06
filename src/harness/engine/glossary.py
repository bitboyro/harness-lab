"""Plain-language definitions for every term the reports use.

A report nobody can read is not a result. Everything here is written for someone
who has never seen this project: no statistics background assumed, and each
entry says what the number means *and* what it would mean to act on it.

Kept in one place so the text report, the HTML report and any future renderer
say the same thing — a term explained twice is a term that eventually gets
explained two different ways.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Term:
    name: str
    short: str
    #: The longer version, including why it is here rather than a simpler number.
    long: str = ""

    def render(self, width: int = 22) -> str:
        return f"    {self.name:<{width}} {self.short}"


GLOSSARY: tuple[Term, ...] = (
    # ---- the shape of the experiment ----
    Term("arm",
         "One way of packaging the API. The thing being compared.",
         "Every arm gets the same tasks against the same API. The only "
         "difference is how the API is presented to the model — as MCP tools, "
         "as written docs it curls, as a code library, and so on."),
    Term("task", "One question or instruction given to the model."),
    Term("core",
         "One navigation problem, reused across five task types.",
         "The same 'find episode X' problem appears as a read, three kinds of "
         "write, and a bulk operation. Because the difficulty of finding the "
         "target is identical across all five, any difference between them is "
         "caused by what happens AFTER it is found — not by one being harder "
         "to locate."),
    Term("run", "One arm attempting one task once."),

    # ---- the controls ----
    Term("Z0",
         "Control: the model gets NO tools at all.",
         "It measures what the model already knew before you gave it anything. "
         "On a made-up API this should be ~0 — if it is not, the API leaked "
         "into the model's training and every result is void. On a real API it "
         "is often high, and then the tools have to beat it to be worth having."),
    Term("Z1",
         "Ceiling: the correct API responses are handed over up front.",
         "The model does no tool use — it just reads the data and answers. If "
         "Z1 scores 80%, then 80% is the best any packaging could do, and an "
         "arm at 75% is nearly perfect rather than mediocre. Without it you "
         "cannot tell a bad wrapper from an impossible task."),

    # ---- the headline numbers ----
    Term("success rate",
         "Share of tasks the arm got right.",
         "Excludes runs that ran out of turns — those are a budget problem, "
         "not a wrong answer."),
    Term("lift",
         "Success rate MINUS Z0's. How much the packaging actually added.",
         "An arm at 67% sounds fine until you learn Z0 scored 83% — then it is "
         "17 points WORSE than giving the model nothing. Raw success can flatter; "
         "lift cannot."),
    Term("pp",
         "Percentage points — the gap between two percentages.",
         "70% minus 55% is 15 pp. Writing '15%' would be ambiguous, because "
         "15% OF 55% is 8.25%. 'pp' says plainly that one was subtracted from "
         "the other."),
    Term("truncated",
         "The run hit its turn limit before answering.",
         "Not counted as wrong — it might have been one step away. Reported "
         "separately, because a high truncation rate is its own finding: the "
         "arm is spending its budget without finishing."),

    # ---- answer or abstain ----
    Term("TP / true positive", "Answerable task, answered correctly."),
    Term("FP / false positive",
         "A task with NO valid answer, and the model made one up.",
         "The dangerous failure. About 15% of tasks are deliberately "
         "unanswerable to catch exactly this."),
    Term("TN / true negative", "Unanswerable task, correctly declined."),
    Term("FN / false negative", "Answerable task, and the model failed or gave up."),
    Term("precision",
         "Of the answers it gave, how many were right.",
         "Low precision means it answers when it should stay quiet. "
         "TP / (TP + FP)."),
    Term("recall",
         "Of the answerable tasks, how many it actually answered.",
         "Low recall means it gives up too easily. TP / (TP + FN)."),
    Term("specificity",
         "Of the unanswerable tasks, how many it correctly refused.",
         "Low specificity means it invents answers. This is the safety number."),
    Term("F1",
         "Precision and recall combined into one score.",
         "Useful as a summary, but it ignores true negatives — so an agent that "
         "correctly refuses gets no credit for it here. Read specificity too."),
    Term("accuracy",
         "Share of ALL decisions that were right.",
         "Misleading when most tasks are answerable: a model that answers "
         "everything scores ~85% accuracy while being maximally unsafe."),
    Term("balanced accuracy",
         "The average of recall and specificity.",
         "Treats 'answered correctly' and 'refused correctly' as equally "
         "important, which fixes accuracy's blind spot."),
    Term("MCC",
         "One number from -1 to +1 summarising the whole 2x2.",
         "+1 is perfect, 0 is no better than guessing, negative is worse than "
         "guessing. Unlike accuracy it cannot be gamed by always answering — "
         "that agent scores 0. The honest single number when unanswerable "
         "tasks are rare."),
    Term("silent failure",
         "Wrong, and stated confidently rather than hedged.",
         "Being wrong is bad; being wrong and convincing is worse, because "
         "nobody downstream will check."),

    # ---- effort and cost ----
    Term("turns", "Round trips between the model and the tools."),
    Term("calls", "Individual API operations the model invoked."),
    Term("static tokens",
         "Tokens spent before the model does anything.",
         "Tool schemas plus any skill or docs. An arm that loads 200 operation "
         "schemas pays for all of them on every single task."),
    Term("cached",
         "Share of input tokens billed at the cheaper cached rate.",
         "Repeated prefixes get discounted. Writing the cache costs MORE than "
         "fresh input, so it only pays off from the second run onward."),
    Term("$/success",
         "Total spend divided by tasks solved.",
         "The comparable figure — dollars, not tokens, because different "
         "providers count tokens differently."),
    Term("harm",
         "Runs that destroyed data or attempted a forbidden operation.",
         "Counts blocked attempts too: on a real API there would be no guard, "
         "so the attempt is the finding."),

    # ---- statistics ----
    Term("95% CI",
         "The range the true value plausibly sits in.",
         "A wide interval means too little data to say much. If it spans zero, "
         "the difference could just as easily be nothing."),
    Term("MDE",
         "Minimum detectable effect — the smallest gap this run could spot.",
         "With few tasks, only huge differences show up. A gap smaller than "
         "the MDE is not a finding, however suggestive the bar looks."),
    Term("p value",
         "Roughly: how easily chance alone could produce this gap.",
         "Below 0.05 is the usual bar. It says nothing about whether the "
         "difference is large enough to care about — that is the CI's job."),
    Term("Holm correction",
         "Adjusts p values for testing several things at once.",
         "Test six comparisons and one will look impressive by luck. This "
         "raises the bar so that does not happen."),
    Term("confirmatory",
         "A comparison declared BEFORE the run, in code.",
         "Only these can be called significant. Deciding what to test after "
         "seeing results is how noise becomes a headline."),
    Term("exploratory",
         "A comparison looked at afterwards.",
         "Reported and labelled, never called significant. It can suggest the "
         "next experiment; it cannot support a claim."),
    Term("paired within core",
         "Arms compared only on problems they both attempted.",
         "A hard problem drags every arm down, so comparing them on the same "
         "problems cancels that out."),
    Term("refusing to pool",
         "Results that must not be averaged together.",
         "Different model, different protocol version, or a hand-written vs "
         "generated skill — averaging those answers a question nobody asked."),
    Term("unvalidated",
         "The metric is computed, but not yet checked against ground truth.",
         "It describes what happened. It is not yet evidence of quality."),
)

_BY_NAME = {t.name: t for t in GLOSSARY}


def lookup(name: str) -> Term | None:
    return _BY_NAME.get(name)


def render_text(width: int = 22) -> str:
    """The glossary as an indented block for the terminal report."""
    lines = ["  what the terms mean:"]
    lines.extend(t.render(width) for t in GLOSSARY)
    return "\n".join(lines)
