#!/usr/bin/env python3
"""Extract a deterministic insights brief from a harness results directory.

Prints JSON to stdout. Numbers come only from the ledger + harness Report —
never invent values in the narrative layer.

Usage:
    python .cursor/skills/harness-insights/scripts/extract_brief.py results/matrix-10
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def _pct(x: float | None, digits: int = 0) -> str | None:
    if x is None:
        return None
    return f"{100 * x:.{digits}f}%"


def _money(x: float | None) -> str | None:
    if x is None:
        return None
    return f"${x:.4f}"


def _secs(x: float | None) -> str | None:
    if x is None:
        return None
    return f"{x:.1f}"


def _short_desc(name: str) -> str:
    """Compress arm display name for the ladder."""
    n = name.lower()
    bits: list[str] = []
    if "sandbox" in n or "code" in n:
        bits.append("sandbox")
    elif "bash" in n or "docs" in n:
        bits.append("bash + docs")
    elif "discovery" in n:
        bits.append("discovery")
    elif "all tools" in n or "mcp" in n:
        bits.append("all tools" if "all tools" in n else "MCP")
    elif "no tools" in n:
        bits.append("no tools")
    elif "handed" in n or "answers" in n:
        bits.append("answers handed over")
    if "authored" in n:
        bits.append("authored")
    elif "skill" in n and "authored" not in n:
        bits.append("generated" if "generated" not in n else "skill")
    return " + ".join(bits) if bits else name


def _cluster_fail(detail: str, task_class: str) -> str:
    d = (detail or "").lower()
    if "tags" in d and ("expected" in d or "found" in d):
        return "Incomplete fan-out tags"
    if "archived" in d and "expected true" in d:
        return "Missed archive"
    if "rating" in d or ".status:" in d or "status:" in d:
        return "Rating / status patch wrong or skipped"
    if "answer does not contain" in d or "answer " in d:
        return "Wrong read answer"
    if "clobber" in d or "runtime_seconds" in d and "expected" in d and "0" in d:
        return "Destructive replace / wiped fields"
    # Fall back to task class bucket
    labels = {
        "R": "Wrong read answer",
        "RW-fan": "Incomplete fan-out write",
        "W-irrev": "Missed or wrong irreversible write",
        "W-lossy": "Lossy write missed or wrong",
        "W-safe": "Safe write missed or wrong",
        "U": "Failed unanswerable handling",
    }
    return labels.get(task_class, f"Other ({task_class})")


def _packaging_pairs(arms: dict[str, Any]) -> list[dict[str, Any]]:
    """Pair generated/none baseline with authored sibling when both exist."""
    names = set(arms)
    pairs: list[dict[str, Any]] = []
    for authored in sorted(n for n in names if n.endswith("-auth")):
        base = authored.removesuffix("-auth")
        # Prefer generated sibling (B1, D2); else bare packaging (rare).
        baseline = base if base in names else None
        if baseline is None:
            continue
        a, b = arms[authored], arms[baseline]
        if a["success"] is None or b["success"] is None:
            continue
        delta = {
            "family": base,
            "baseline": baseline,
            "authored": authored,
            "success_pp": round(100 * (a["success"] - b["success"]), 1),
            "abstention_pp": None,
            "fp_baseline": b["false_positives"],
            "fp_authored": a["false_positives"],
        }
        if a["abstention"] is not None and b["abstention"] is not None:
            delta["abstention_pp"] = round(
                100 * (a["abstention"] - b["abstention"]), 1)
        pairs.append(delta)
    return pairs


def _pick_careful(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Precision / no-hallucination / no-harm first; money and time ignored."""
    if not candidates:
        return None

    def key(a: dict[str, Any]) -> tuple:
        return (
            a["precision"] if a["precision"] is not None else -1,
            a["abstention"] if a["abstention"] is not None else -1,
            -a["false_positives"],
            -a["harm_events"],
            a["success"] if a["success"] is not None else -1,
        )

    return max(candidates, key=key)


def _pick_fastest(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    timed = [a for a in candidates if a["mean_secs"] is not None]
    if not timed:
        return None
    return min(timed, key=lambda a: a["mean_secs"])


def _pick_cheapest(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    priced = [a for a in candidates if a["cost_per_success"] is not None]
    if not priced:
        return None
    return min(priced, key=lambda a: a["cost_per_success"])


def _repo_root() -> Path:
    # .cursor/skills/harness-insights/scripts/this.py → five parents up
    return Path(__file__).resolve().parents[4]


def _load_report(results_dir: Path):
    """Prefer the harness Report so numbers match `harness report`."""
    repo = _repo_root()
    src = repo / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from harness.engine.analysis import Report  # type: ignore
    from harness.engine.results import ResultStore  # type: ignore

    store = ResultStore(results_dir)
    rows = list(store.rows())
    if not rows:
        raise SystemExit(f"no results in {results_dir}")
    manifest = store.manifest()
    mde_pp = None
    if manifest.get("cores"):
        try:
            from harness.experiment.power import Contrast, analyse  # type: ignore
            mde_pp = analyse(
                Contrast.MAIN_EFFECT,
                int(manifest["cores"]),
                repeats=int(manifest.get("repeats", 1)),
            ).mde_pp
        except Exception:  # noqa: BLE001 — missing MDE only drops one note
            mde_pp = None
    return Report(rows=rows, manifest=manifest, mde_pp=mde_pp), manifest


def build_brief(results_dir: Path) -> dict[str, Any]:
    report, manifest = _load_report(results_dir)
    pricing = report.pricing
    verdict = report.verdict()

    arms_out: dict[str, Any] = {}
    for name, arm in report.arms.items():
        conf = arm.confusion
        peak = arm.metric_mean("peak_context_tokens")
        calls = arm.mean("calls")
        # Peak / calls on successful runs only — efficiency story.
        succ_rows = [r for r in arm.graded if r["outcome"] in ("pass", "correct-refusal")]
        peak_succ = None
        calls_succ = None
        if succ_rows:
            peaks = [r["metrics"]["peak_context_tokens"]
                     for r in succ_rows
                     if isinstance(r.get("metrics", {}).get("peak_context_tokens"),
                                   (int, float))]
            callsv = [r["calls"] for r in succ_rows
                      if isinstance(r.get("calls"), (int, float))]
            peak_succ = sum(peaks) / len(peaks) if peaks else None
            calls_succ = sum(callsv) / len(callsv) if callsv else None

        cps = arm.cost_per_success(pricing)
        arms_out[name] = {
            "arm": name,
            "name": arm.name,
            "short": _short_desc(arm.name),
            "is_control": arm.is_control,
            "skill_condition": next(
                (r.get("skill_condition") for r in arm.rows), None),
            "n": arm.n,
            "graded": len(arm.graded),
            "success": arm.success_rate,
            "success_pct": _pct(arm.success_rate),
            "abstention": arm.abstention_accuracy,
            "abstention_pct": _pct(arm.abstention_accuracy),
            "precision": conf.precision,
            "precision_pct": _pct(conf.precision),
            "false_positives": conf.fp,
            "true_positives": conf.tp,
            "correct_refusals": conf.tn,
            "harm_events": arm.harm_events,
            "harm_rate": arm.harm_rate,
            "harm_pct": _pct(arm.harm_rate),
            "truncation_rate": arm.truncation_rate,
            "truncation_pct": _pct(arm.truncation_rate),
            "mean_secs": arm.mean("wall_clock_seconds"),
            "mean_secs_fmt": _secs(arm.mean("wall_clock_seconds")),
            "cost_per_success": cps,
            "cost_per_success_fmt": _money(cps),
            "mean_peak_tokens": peak,
            "mean_calls": calls,
            "succ_peak_tokens": peak_succ,
            "succ_calls": calls_succ,
            "composite_score": verdict.scores.get(name),
            "lift_pp": (round(100 * report.lift(name), 1)
                        if report.lift(name) is not None else None),
        }

    packaging = [a for a in arms_out.values() if not a["is_control"]]
    careful = _pick_careful(packaging)
    fastest = _pick_fastest(packaging)
    cheapest = _pick_cheapest(packaging)

    winner_name = verdict.winner
    winner = arms_out.get(winner_name) if winner_name else careful

    # Fail clusters for the careful / winner arm
    fail_arm = (careful or winner or {}).get("arm")
    fail_clusters: list[dict[str, Any]] = []
    if fail_arm and fail_arm in report.arms:
        buckets: Counter[str] = Counter()
        samples: dict[str, str] = {}
        for r in report.arms[fail_arm].graded:
            if r["outcome"] != "fail":
                continue
            label = _cluster_fail(r.get("detail") or "", r.get("task_class") or "")
            buckets[label] += 1
            samples.setdefault(label, (r.get("detail") or "")[:160])
        fail_clusters = [
            {"label": lab, "n": n, "sample": samples[lab]}
            for lab, n in buckets.most_common()
        ]
        miss_n = sum(buckets.values())
    else:
        miss_n = 0

    # Discovery vs eager truncation contrast
    discovery = [a for a in packaging
                 if "discovery" in (a["name"] or "").lower()
                 or a["arm"] in ("A2", "B2", "B2-auth")]
    eager_or_code = [a for a in packaging
                     if a not in discovery]
    trunc_discovery = (
        round(100 * sum(a["truncation_rate"] for a in discovery) / len(discovery), 0)
        if discovery else None)
    trunc_other = (
        round(100 * sum(a["truncation_rate"] for a in eager_or_code) / len(eager_or_code), 0)
        if eager_or_code else None)

    # Authored skill deltas
    pairs = _packaging_pairs(arms_out)
    success_deltas = [p["success_pp"] for p in pairs]
    abstain_deltas = [p["abstention_pp"] for p in pairs
                      if p["abstention_pp"] is not None]

    created = manifest.get("created_at")
    date_label = None
    if created:
        try:
            date_label = datetime.fromisoformat(
                created.replace("Z", "+00:00")).strftime("%b %-d, %Y")
        except ValueError:
            date_label = str(created)[:10]

    # Ladder: success desc, controls included, collapse near-ties optionally left to agent
    ladder = sorted(
        arms_out.values(),
        key=lambda a: (-(a["success"] or -1), a["arm"]),
    )

    # Clobber fingerprint from any packaging arm with harm
    clobber_fields: Counter[str] = Counter()
    for arm in report.arms.values():
        if arm.is_control:
            continue
        for r in arm.rows:
            for path in r.get("clobbered") or []:
                # $.episodes.ep_x.title → title
                field = str(path).rsplit(".", 1)[-1]
                clobber_fields[field] += 1

    brief = {
        "run": {
            "id": manifest.get("id") or report.run_id,
            "dir": str(results_dir),
            "model": report.model,
            "provider": manifest.get("provider"),
            "reasoning_effort": manifest.get("reasoning_effort"),
            "difficulty": manifest.get("difficulty"),
            "tasks": manifest.get("tasks") or report.task_count,
            "repeats": manifest.get("repeats"),
            "cores": manifest.get("cores"),
            "planned": manifest.get("planned") or len(report.rows),
            "n_rows": len(report.rows),
            "presets": manifest.get("presets") or sorted(report.arms),
            "mde_pp": report.mde_pp,
            "date_label": date_label,
            "incomplete_arms": {
                k: {"have": v[0], "expected": v[1]}
                for k, v in report.incomplete_arms.items()
            },
            "pooling_refused": report.pooling_refused,
            "baseline_success": report.baseline,
            "baseline_success_pct": _pct(report.baseline),
        },
        "verdict": {
            "winner": winner_name,
            "leader": verdict.leader,
            "runner_up": verdict.runner_up,
            "reason": verdict.reason,
            "scores": {k: round(v, 2) for k, v in verdict.scores.items()},
            "caveats": list(verdict.caveats),
        },
        "arms": arms_out,
        "ladder": [
            {
                "arm": a["arm"],
                "short": a["short"],
                "name": a["name"],
                "success_pct": a["success_pct"],
                "success": a["success"],
                "is_control": a["is_control"],
                "is_winner": a["arm"] == winner_name,
            }
            for a in ladder
        ],
        "picks": {
            "careful": careful,
            "fastest": fastest,
            "cheapest": cheapest,
        },
        "skill_deltas": {
            "pairs": pairs,
            "success_pp_range": (
                [min(success_deltas), max(success_deltas)]
                if success_deltas else None),
            "abstention_pp_range": (
                [min(abstain_deltas), max(abstain_deltas)]
                if abstain_deltas else None),
            "authored_zero_fp": all(
                arms_out[p["authored"]]["false_positives"] == 0 for p in pairs
            ) if pairs else None,
        },
        "mechanisms": {
            "truncation_discovery_pct_avg": trunc_discovery,
            "truncation_other_pct_avg": trunc_other,
            "discovery_arms": [a["arm"] for a in discovery],
            "clobber_fields": dict(clobber_fields.most_common(8)),
        },
        "winner_failures": {
            "arm": fail_arm,
            "misses": miss_n,
            "graded": arms_out[fail_arm]["graded"] if fail_arm else 0,
            "clusters": fail_clusters,
        },
    }
    return brief


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path, help="results directory with results.jsonl")
    ap.add_argument("--pretty", action="store_true", help="indent JSON")
    args = ap.parse_args()
    if not args.results.is_dir():
        print(f"not a directory: {args.results}", file=sys.stderr)
        return 2
    brief = build_brief(args.results.resolve())
    print(json.dumps(brief, indent=2 if args.pretty else None, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
