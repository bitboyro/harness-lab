#!/usr/bin/env python3
"""Success/failure counts split three ways: by core, by task, by repeat.

    .venv/bin/python scripts/breakdown.py results/baseline-experiment-80 -o DIR

Writes three independent CSVs — `core.csv`, `task.csv`, `repeat.csv`. Separate
from `analyze.py` on purpose: that file answers "which arm won", this one answers
"which problems were hard and did the answer hold up when asked again", which is
a question about the *suite*, not the packaging.

Success is `pass` + `correct-refusal`, the same definition the report uses, taken
from the engine rather than restated here. Infra errors get their own column
instead of being folded into failures: a run killed by a dead key measured
nothing, and counting it as a failure would blame the task for the machine.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from harness.engine.analysis import SUCCESS  # noqa: E402
from harness.engine.results import ResultStore  # noqa: E402

NA = "n/a"


def _tally(rows: list[dict]) -> tuple[int, int, int, int, float | None]:
    """(total, graded, success, failure, rate) — rate over graded runs only."""
    infra = sum(1 for r in rows if r["outcome"] == "infra-error")
    graded = len(rows) - infra
    ok = sum(1 for r in rows if r["outcome"] in SUCCESS)
    return len(rows), graded, ok, graded - ok, (ok / graded if graded else None)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("results", type=Path)
    p.add_argument("-o", "--out", type=Path, required=True,
                   help="directory for core.csv, task.csv, repeat.csv")
    args = p.parse_args(argv)

    store = ResultStore(args.results)
    rows = list(store.rows())
    args.out.mkdir(parents=True, exist_ok=True)

    def write(name: str, headers: list[str], data: list[list]) -> None:
        with (args.out / name).open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(headers)
            w.writerows(data)
        print(f"{name:12} {len(data):5} rows")

    # ---- by core ----------------------------------------------------------
    by_core: dict[str, list] = defaultdict(list)
    for r in rows:
        by_core[r["core_id"]].append(r)
    core_rows = []
    for core, rs in by_core.items():
        total, graded, ok, bad, rate = _tally(rs)
        core_rows.append([
            core,
            "no" if "unanswerable" in str(core) else "yes",
            len({r["task_id"] for r in rs}), len({r["arm"] for r in rs}),
            total, graded, ok, bad, total - graded,
            (round(rate, 6) if rate is not None else NA),
        ])
    core_rows.sort(key=lambda r: (r[9] if r[9] != NA else -1))
    write("core.csv",
          ["core_id", "answerable", "tasks", "arms", "total", "graded",
           "success", "failure", "infra", "success_rate"], core_rows)

    # ---- by task ----------------------------------------------------------
    # The per-repeat columns are the point: a task that flips between repeats is
    # a different kind of hard than one that fails all three the same way.
    by_task: dict[str, list] = defaultdict(list)
    for r in rows:
        by_task[r["task_id"]].append(r)
    repeat_ids = sorted({r["repeat"] for r in rows})
    task_rows = []
    for task, rs in by_task.items():
        total, graded, ok, bad, rate = _tally(rs)
        per_rep = []
        for i in repeat_ids:
            sub = [r for r in rs if r["repeat"] == i]
            if not sub:                       # this repeat was never run
                per_rep += [NA, NA]
                continue
            _, g, o, _, rr = _tally(sub)
            per_rep += [o, (round(rr, 6) if rr is not None else NA)]
        first = rs[0]
        task_rows.append([
            task, first["core_id"], str(first["task_class"]),
            "yes" if first.get("answerable") else "no",
            len({r["arm"] for r in rs}),
            total, graded, ok, bad, total - graded,
            (round(rate, 6) if rate is not None else NA),
            *per_rep,
        ])
    task_rows.sort(key=lambda r: (r[10] if r[10] != NA else -1))
    rep_cols = [c for i in repeat_ids for c in (f"r{i}_success", f"r{i}_rate")]
    write("task.csv",
          ["task_id", "core_id", "task_class", "answerable", "arms",
           "total", "graded", "success", "failure", "infra", "success_rate",
           *rep_cols], task_rows)

    # ---- by repeat --------------------------------------------------------
    # Split per arm as well as overall: a drift between repeat 0 and repeat 2
    # would mean the world was not reset cleanly, which is a rig bug, not a
    # finding — so it is worth being able to see it.
    rep_rows = []
    for i in repeat_ids:
        sub = [r for r in rows if r["repeat"] == i]
        total, graded, ok, bad, rate = _tally(sub)
        rep_rows.append(["ALL", i, total, graded, ok, bad, total - graded,
                         (round(rate, 6) if rate is not None else NA)])
    for arm in sorted({r["arm"] for r in rows}):
        for i in repeat_ids:
            sub = [r for r in rows if r["arm"] == arm and r["repeat"] == i]
            if not sub:
                rep_rows.append([arm, i, 0, 0, 0, 0, 0, NA])
                continue
            total, graded, ok, bad, rate = _tally(sub)
            rep_rows.append([arm, i, total, graded, ok, bad, total - graded,
                             (round(rate, 6) if rate is not None else NA)])
    write("repeat.csv",
          ["arm", "repeat", "total", "graded", "success", "failure", "infra",
           "success_rate"], rep_rows)

    print(f"\nwrote to {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
