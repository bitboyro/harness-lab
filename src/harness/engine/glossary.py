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
    Term("infra-error",
         "The harness, provider or machine broke — the arm was never measured.",
         "A full disk, an expired API key, a provider timeout. Excluded from "
         "every rate, because counting a full disk as a packaging failure "
         "makes an arm look worse than it is. Carries an error_kind saying "
         "which, and --resume re-runs these cells rather than skipping them."),

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
         "Low specificity means it invents answers. This is the safety number. "
         "Also shown as 'abstain' in the ranked tables."),
    Term("abstain / abstention",
         "The same number as specificity, under a plainer name.",
         "Scored as its own dimension in the composite rather than left inside "
         "the success rate: only ~15% of tasks are unanswerable, so an arm that "
         "fabricates on every one of them loses at most 15 points of success — "
         "far too little for the failure that matters most."),
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

    # ---- the ranking ----
    Term("SCORE / composite",
         "Every dimension rescaled 0-1, then weighted into one number.",
         "A decision aid, not evidence. It will always produce a ranking, "
         "including one made entirely of noise — which is why the winner is "
         "printed with whether its lead is larger than the MDE. Read the score "
         "to shortlist; read the interval before acting."),
    Term("weights",
         "How much each dimension counts toward the score.",
         "Default: success .35, abstention .15, harm .25, cost .15, time .10 — "
         "so safety (.40 combined) outweighs thrift (.25) and an arm cannot buy "
         "its way to the top by being cheap and dangerous. Override with "
         "--weights; they are always printed beside the table."),
    Term("candidate arm",
         "An arm eligible to win: a packaging you could actually ship.",
         "Z0 and Z1 are excluded. They anchor the scale rather than competing "
         "on it, and letting the ceiling arm into the range would squash every "
         "real arm into the bottom of the scale."),
    Term("spread",
         "How much a behavioural metric separated the arms.",
         "Decides which metrics get charted. Deliberately not a coefficient of "
         "variation: one arm at 0.15 against eight at zero would score huge and "
         "outrank a metric running 0 to 2.8 across four arms — that separated "
         "one arm, not the arms."),

    # ---- how each arm behaved ----
    Term("discovery overhead",
         "Calls made before the first one that returned usable data.",
         "A discovery arm pays this by design; the question is whether it earns "
         "it back in fewer wasted calls later."),
    Term("wasted calls",
         "Responses whose content never reaches the final answer.",
         "Data fetched and then ignored. Every one filled the context window "
         "for nothing, and it is usually the clearest sign that a surface "
         "returns more than the task needs."),
    Term("redundant calls",
         "The identical request issued more than once in one run.",
         "The model is not retaining what it already fetched and is paying "
         "twice. High counts usually mean the response was too big to hold "
         "onto, not that the model was careless."),
    Term("payload efficiency",
         "Of everything the API returned, the share used in the answer.",
         "Low means responses are far larger than the task needs. Fixing it is "
         "an API change — sparser responses — not a packaging change."),
    Term("argument validity",
         "Share of calls the API accepted rather than rejecting as malformed.",
         "Low means the schema is not telling the model how to call it. This is "
         "the number a richer schema should move."),
    Term("error recovery rate",
         "Of the calls the API rejected, how many it then got right.",
         "The mechanism by which better error messages would beat shipping a "
         "skill: an error only helps if it says enough to act on."),
    Term("hallucinated endpoints",
         "Calls to operations that do not exist.",
         "The model invented them rather than reading the surface — evidence "
         "that discovery is failing, not that the model is careless."),
    Term("peak context tokens",
         "The largest the context window got during the run.",
         "What would have to fit if you pointed this packaging at a bigger "
         "problem. An arm near the limit here will break on a harder task."),
    Term("turns to first productive call",
         "How long before the model got anything useful out of the API.",
         "Measures how quickly a packaging becomes usable, which is not the "
         "same as how well it ends up performing."),

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

    # ---- comparing runs ----
    Term("reference run",
         "The first directory you passed. Every delta is measured against it.",
         "Swapping the order flips every sign. The reference is named in the "
         "header so a reader never has to guess which way a difference points."),
    Term("Δ / delta",
         "This run minus the reference, in the unit the difference is in.",
         "Rates become percentage points (pp), never a percentage of a "
         "percentage. An absent number is n/a, never zero — a blank that "
         "reads as zero is a claim nobody measured."),
    Term("shared arm",
         "An arm every compared run actually ran.",
         "Only shared arms enter the head-to-head. An arm two runs out of "
         "three have would leave a blank in a delta column, and a blank "
         "reads as a zero."),
    Term("not compared",
         "Arms missing from at least one run, shown standalone.",
         "They are excluded from every delta rather than shown with a blank "
         "cell. Their numbers are still reported — just not subtracted."),
    Term("not recorded",
         "This run's ledger cannot say what the parameter was.",
         "Not the same as equal. Two runs that both cannot say might still "
         "have differed, and reporting that as a match is the lie the "
         "sentinel exists to prevent. Common on ledgers written before a "
         "manifest field existed."),
    Term("same world",
         "Both runs were given the same generated tasks.",
         "Core ids are positional; core-000 in one world is a different "
         "problem from core-000 in another. Pairing across worlds would "
         "produce a tighter interval than the data supports — the most "
         "dangerous direction for an error to go."),
    Term("unpaired comparison",
         "A cross-run gap computed without pairing within core.",
         "The common case when two runs used different seeds, cores, or "
         "difficulty. Per-task difficulty no longer cancels, so the gap may "
         "be biased rather than merely noisy. Always labelled, never called "
         "significant."),
    Term("cross-world delta",
         "A difference across a pooling boundary — model, MCP revision, "
         "skill condition, or report class.",
         "The rates are real; their difference is not a finding. Marked ‡ "
         "and never called notable, however large the gap."),
    Term("cross-run MDE",
         "The smallest gap these two samples could resolve, in points.",
         "Larger than either run's own MDE: both measurements carry error "
         "and errors add (≈√(a²+b²)). An approximation, not a derivation "
         "from the power model, and labelled as one wherever it appears."),
    Term("parameter diff",
         "What differed in the setup before any result is shown.",
         "A delta table read without knowing the runs used different "
         "difficulty is worse than no table. Differs means two runs "
         "recorded different values; not recorded somewhere is uncertainty, "
         "not disagreement."),
    Term("confidence interval",
         "The range the true difference plausibly sits in.",
         "For unpaired cross-run gaps this is a Newcombe hybrid-score "
         "interval, not the textbook Wald form — Wald collapses at the "
         "edges and makes a 2-for-2 smoke arm look like a finding."),
)

_BY_NAME = {t.name: t for t in GLOSSARY}


def lookup(name: str) -> Term | None:
    return _BY_NAME.get(name)


def render_text(width: int = 22) -> str:
    """The glossary as an indented block for the terminal report."""
    lines = ["  what the terms mean:"]
    lines.extend(t.render(width) for t in GLOSSARY)
    return "\n".join(lines)
