"""Read progress off a results directory, without touching the running job.

A matrix takes tens of minutes. The ledger is appended per run, so progress is
already on disk — this just reads it, which means a second terminal can check on
a run without interrupting it or relying on the log catching up.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Progress:
    done: int
    expected: int | None
    by_arm: dict[str, int]
    started_at: datetime | None
    elapsed_seconds: float
    outcomes: dict[str, int]

    @property
    def fraction(self) -> float | None:
        if not self.expected:
            return None
        return min(1.0, self.done / self.expected)

    @property
    def eta_seconds(self) -> float | None:
        if not self.expected or not self.done or self.done >= self.expected:
            return None
        rate = self.elapsed_seconds / self.done
        return rate * (self.expected - self.done)

    def render(self) -> str:
        lines = []
        if self.fraction is not None:
            bar_width = 28
            filled = int(self.fraction * bar_width)
            bar = "█" * filled + "·" * (bar_width - filled)
            eta = self.eta_seconds
            eta_text = ("done" if eta is None
                        else f"eta {eta / 60:.0f}m" if eta >= 60
                        else f"eta {eta:.0f}s")
            lines.append(f"  {bar}  {self.done}/{self.expected} "
                         f"({self.fraction:.0%})  {eta_text}")
        else:
            lines.append(f"  {self.done} runs recorded "
                         "(no manifest, so no total to compare against)")

        lines.append(f"  elapsed {self.elapsed_seconds / 60:.0f}m")
        if self.by_arm:
            lines.append("")
            lines.append("  per arm: " + "  ".join(
                f"{arm} {n}" for arm, n in sorted(self.by_arm.items())))
        if self.outcomes:
            lines.append("  outcomes: " + "  ".join(
                f"{name} {n}" for name, n in sorted(self.outcomes.items())))
        return "\n".join(lines)


def read(directory: str | Path) -> Progress:
    root = Path(directory)
    ledger = root / "results.jsonl"
    rows = []
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))

    manifest = {}
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    # A ledger can legitimately hold MORE rows than a naive arms x tasks count
    # when cells are skipped, and fewer when they are not. Trust the recorded
    # plan; fall back only for ledgers written before it existed, and never let
    # the fallback report a total below what is already on disk.
    expected = manifest.get("planned")
    if expected is None and manifest.get("presets") and manifest.get("tasks"):
        # Fallback for older ledgers. Over-counts when cells were skipped.
        expected = (len(manifest["presets"]) * int(manifest["tasks"])
                    * int(manifest.get("repeats", 1)))
    expected = int(expected) if expected else None
    if expected is not None and expected < len(rows):
        expected = len(rows)

    started_at = None
    elapsed = 0.0
    if manifest.get("created_at"):
        started_at = datetime.fromisoformat(manifest["created_at"])
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    return Progress(
        done=len(rows),
        expected=expected,
        by_arm=dict(Counter(r["arm"] for r in rows)),
        started_at=started_at,
        elapsed_seconds=elapsed,
        outcomes=dict(Counter(r["outcome"] for r in rows)),
    )
