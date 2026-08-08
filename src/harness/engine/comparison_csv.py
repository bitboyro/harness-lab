"""Three CSV files for one comparison.

`arms.csv` is the analysed view, `params.csv` the setup, `rows.csv` the raw
ledger. All three carry a leading `run` column so a reader can join them.

Fieldnames for `rows.csv` are the union across every run. Taking them from the
first row alone — which is what `report --csv` does today — raises ValueError
the moment an older ledger is mixed with a newer one. That bug is not fixed
here; it is simply not reproduced.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .comparison import NOT_RECORDED, Comparison, PARAMETERS

#: Stable leading columns for the flattened ledger. Everything else follows in
#: sorted order so two comparisons of the same runs produce the same header.
_ROW_LEAD = (
    "run", "run_id", "arm", "task_id", "core_id", "task_class", "answerable",
    "repeat", "outcome", "detail", "confident", "turns", "calls",
    "forbidden_attempts", "truncated", "error", "error_kind",
    "wall_clock_seconds", "input_tokens", "cached_input_tokens",
    "output_tokens", "reasoning_tokens", "static_tokens",
    "per_call_overhead_tokens", "session_setup_tokens", "model",
    "mcp_spec_revision", "skill_condition", "report_class", "seed",
    "surface_size",
)

_ARM_FIELDS = (
    "run", "path", "arm", "name", "is_control", "shared", "n", "graded",
    "success_rate", "ci_lo", "ci_hi", "lift", "abstention", "harm_events",
    "harm_rate", "truncation_rate", "silent_failure_rate", "cost_total_usd",
    "cost_per_success", "cache_hit_rate", "mean_turns", "mean_calls",
    "mean_input_tokens", "mean_cached_input_tokens", "mean_output_tokens",
    "mean_reasoning_tokens", "mean_static_tokens", "mean_wall_clock_seconds",
    "score", "tp", "fp", "tn", "fn_hedged", "fn_confident", "mcc",
)


def write(comparison: Comparison, out: Path | str) -> list[Path]:
    """Write arms.csv, params.csv and rows.csv. Returns what was written."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = [
        _write_arms(comparison, out / "arms.csv"),
        _write_params(comparison, out / "params.csv"),
        _write_rows(comparison, out / "rows.csv"),
    ]
    return written


def _cell(value: Any) -> Any:
    """CSV-safe cell. None and NOT_RECORDED become empty, never the string 'None'."""
    if value is None or value is NOT_RECORDED:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return value


def _write_arms(comparison: Comparison, path: Path) -> Path:
    shared = set(comparison.shared_arms)
    classes: set[str] = set()
    for ref in comparison.runs:
        for summary in ref.report.arms.values():
            classes.update(summary.by_class())
    class_cols = [f"class.{c}" for c in sorted(classes)]
    fieldnames = list(_ARM_FIELDS) + class_cols

    rows: list[dict[str, Any]] = []
    for ref in comparison.runs:
        report = ref.report
        for arm, summary in sorted(report.arms.items()):
            ci = summary.success_ci
            cost = summary.cost(report.pricing)
            confusion = summary.confusion
            by_class = summary.by_class()
            row = {
                "run": ref.label,
                "path": ref.path,
                "arm": arm,
                "name": summary.name,
                "is_control": "yes" if summary.is_control else "no",
                "shared": "yes" if arm in shared else "no",
                "n": summary.n,
                "graded": len(summary.graded),
                "success_rate": _cell(summary.success_rate),
                "ci_lo": _cell(None if ci is None else ci[0]),
                "ci_hi": _cell(None if ci is None else ci[1]),
                "lift": _cell(report.lift(arm)),
                "abstention": _cell(summary.abstention_accuracy),
                "harm_events": summary.harm_events,
                "harm_rate": summary.harm_rate,
                "truncation_rate": summary.truncation_rate,
                "silent_failure_rate": _cell(summary.silent_failure_rate),
                "cost_total_usd": _cell(None if cost is None else cost.total_usd),
                "cost_per_success": _cell(summary.cost_per_success(report.pricing)),
                "cache_hit_rate": _cell(summary.cache_hit_rate()),
                "mean_turns": _cell(summary.mean("turns")),
                "mean_calls": _cell(summary.mean("calls")),
                "mean_input_tokens": _cell(summary.mean("input_tokens")),
                "mean_cached_input_tokens": _cell(
                    summary.mean("cached_input_tokens")),
                "mean_output_tokens": _cell(summary.mean("output_tokens")),
                "mean_reasoning_tokens": _cell(summary.mean("reasoning_tokens")),
                "mean_static_tokens": _cell(summary.mean("static_tokens")),
                "mean_wall_clock_seconds": _cell(
                    summary.mean("wall_clock_seconds")),
                "score": _cell(report.rank_value(arm, "score")),
                "tp": confusion.tp,
                "fp": confusion.fp,
                "tn": confusion.tn,
                "fn_hedged": confusion.fn_abstained,
                "fn_confident": confusion.fn_confident,
                "mcc": _cell(confusion.mcc),
            }
            for col in class_cols:
                cls = col.removeprefix("class.")
                row[col] = _cell(by_class.get(cls))
            rows.append(row)

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_params(comparison: Comparison, path: Path) -> Path:
    param_names = [p.name for p in PARAMETERS]
    fieldnames = ["run", "path", *param_names]
    rows: list[dict[str, Any]] = []
    for ref in comparison.runs:
        row: dict[str, Any] = {"run": ref.label, "path": ref.path}
        for param_row in comparison.params:
            row[param_row.name] = _cell(param_row.values[ref.label])
        rows.append(row)

    differs: dict[str, Any] = {"run": "__differs__", "path": ""}
    for param_row in comparison.params:
        if param_row.differs:
            differs[param_row.name] = "yes"
        elif param_row.uncertain:
            differs[param_row.name] = "unknown"
        else:
            differs[param_row.name] = "no"
    rows.append(differs)

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _flatten_row(run_label: str, row: dict[str, Any]) -> dict[str, Any]:
    """One ledger row with nested dicts pulled into dotted columns."""
    flat: dict[str, Any] = {"run": run_label}
    for key, value in row.items():
        if key == "metrics" and isinstance(value, dict):
            for name, metric in value.items():
                flat[f"metric.{name}"] = metric
        elif key == "axes" and isinstance(value, dict):
            for name, axis in value.items():
                flat[f"axis.{name}"] = axis
        elif key == "clobbered" and isinstance(value, (list, tuple)):
            flat[key] = ",".join(str(v) for v in value)
        elif key == "retries" and isinstance(value, (list, tuple)):
            flat[key] = ",".join(str(v) for v in value)
        else:
            flat[key] = "" if value is None else value
    return flat


def _write_rows(comparison: Comparison, path: Path) -> Path:
    flats = [_flatten_row(ref.label, row)
             for ref in comparison.runs for row in ref.report.rows]
    # Keep every declared lead column that appears, then every other key sorted.
    # Keys present only in some runs still get a column; missing cells stay "".
    seen = {k for flat in flats for k in flat}
    fieldnames = [k for k in _ROW_LEAD if k in seen]
    fieldnames += sorted(seen - set(fieldnames))

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, restval="",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flats)
    return path
