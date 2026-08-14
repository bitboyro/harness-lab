#!/usr/bin/env python3
"""Article charts for baseline-experiment-80 — SVG, no dependencies.

Reads `results/<run>/analysis/*.csv` and writes theme-aware SVGs. Pure stdlib on
purpose: the repo already renders its own SVG (`engine/svg.py`), and a matplotlib
dependency would buy nothing except a heavier venv for eight static figures.

Every figure carries its own <style> block with a `prefers-color-scheme` twin, so
one file works on a light or dark page. Colors are the validated reference
palette; only slots 1–2 are used categorically, which is the subset that clears
the all-pairs CVD gate in both modes.

    python3 scripts/article_charts.py [--run results/baseline-experiment-80]
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

# ---- design tokens (validated reference palette) --------------------------
# Light/dark pairs. Anything that is not a data mark is ink or chrome; data
# marks never borrow ink colors and text never wears a series color.
TOKENS = {
    "surface":  ("#fcfcfb", "#1a1a19"),
    "ink":      ("#0b0b0b", "#ffffff"),
    "ink2":     ("#52514e", "#c3c2b7"),
    "muted":    ("#898781", "#898781"),
    "grid":     ("#e1e0d9", "#2c2c2a"),
    "axis":     ("#c3c2b7", "#383835"),
    "s1":       ("#2a78d6", "#3987e5"),   # categorical slot 1
    "s2":       ("#eb6834", "#d95926"),   # categorical slot 2
    "quiet1":   ("#c9c8c2", "#4a4a46"),   # de-emphasised fills (pie tail)
    "quiet2":   ("#d8d7d2", "#3d3d39"),
    "quiet3":   ("#e4e3de", "#343431"),
    "quiet4":   ("#eeede9", "#2c2c29"),
}

# Sequential blue ramp, light→dark. Magnitude only — never on nominal categories.
RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
        "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95"]

FONT = 'system-ui,-apple-system,"Segoe UI",sans-serif'


def style_block() -> str:
    light = "\n".join(f"    --{k}: {v[0]};" for k, v in TOKENS.items())
    dark = "\n".join(f"      --{k}: {v[1]};" for k, v in TOKENS.items())
    return f"""<style>
  svg {{
{light}
    font-family: {FONT};
  }}
  @media (prefers-color-scheme: dark) {{
    svg {{
{dark}
    }}
  }}
  .bg {{ fill: var(--surface); }}
  .grid {{ stroke: var(--grid); stroke-width: 1; }}
  .axis {{ stroke: var(--axis); stroke-width: 1; }}
  .tick {{ fill: var(--muted); font-size: 11px; }}
  .lbl {{ fill: var(--ink2); font-size: 12px; }}
  .lbl-strong {{ fill: var(--ink); font-size: 12px; font-weight: 600; }}
  .title {{ fill: var(--ink); font-size: 15px; font-weight: 600; }}
  .sub {{ fill: var(--muted); font-size: 11.5px; }}
  .note {{ fill: var(--muted); font-size: 10.5px; }}
  .s1 {{ fill: var(--s1); }}
  .s2 {{ fill: var(--s2); }}
  .ring {{ stroke: var(--surface); stroke-width: 2; }}
</style>"""


#: Presentation scale. All layout math stays in the design coordinate system
#: (the viewBox); this only sets the intrinsic size an <img> reports, so the
#: figure fills a ~1100px content column instead of sitting at 760 with the
#: chart text too small against body copy. `max-width:100%` still shrinks it on
#: narrow screens, and nothing rasterises — it is vector all the way down.
DISPLAY_SCALE = 1.5


def svg_open(w: int, h: int, title: str, sub: str = "") -> list[str]:
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{round(w * DISPLAY_SCALE)}" height="{round(h * DISPLAY_SCALE)}" '
        f'role="img" aria-label="{esc(title)}">',
        style_block(),
        f'<rect class="bg" x="0" y="0" width="{w}" height="{h}"/>',
        f'<text class="title" x="24" y="30">{esc(title)}</text>',
    ]
    if sub:
        out.append(f'<text class="sub" x="24" y="49">{esc(sub)}</text>')
    return out


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def write(path: Path, parts: list[str]) -> None:
    path.write_text("\n".join(parts) + "\n</svg>\n", encoding="utf-8")
    print(f"wrote {path}")


def read_csv(base: Path, name: str) -> list[dict]:
    with (base / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def f(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


#: Controls are ranked and displayed but never eligible to win, so they are
#: excluded anywhere the figure implies "which packaging should I pick".
CONTROLS = {"Z0", "Z1", "Z-cheat"}


# ---- 1 · safety vs accuracy ----------------------------------------------

def chart_safety_accuracy(A: Path, out: Path) -> None:
    """Two measures, one relationship → scatter. Never a dual-axis bar.

    Identity is carried by direct labels, not by hue: seven categorical colors
    in a scatter cannot clear the all-pairs CVD gate, and the label is a better
    channel here anyway.
    """
    grid = read_csv(A, "verdict_grid.csv")
    pts = [(r["arm"], f(r, "success_raw") * 100, f(r, "harm_raw") * 100)
           for r in grid if r["arm"] not in CONTROLS]

    W, H = 760, 500
    L, R, T, B = 74, 210, 74, 96
    x0, x1 = 63.0, 77.5
    # Headroom above the tallest point and below the lowest so no dot's label
    # collides with an axis band.
    y0, y1 = -0.45, 5.0

    def sx(v): return L + (v - x0) / (x1 - x0) * (W - L - R)
    def sy(v): return H - B - (v - y0) / (y1 - y0) * (H - B - T)

    p = svg_open(W, H, "Nobody holds both corners",
                 "Graded success against harm rate · one dot per packaging arm · "
                 "controls excluded")

    for gv in [0, 1, 2, 3, 4, 5]:
        y = sy(gv)
        p.append(f'<line class="grid" x1="{L}" y1="{y:.1f}" x2="{W-R}" y2="{y:.1f}"/>')
        p.append(f'<text class="tick" x="{L-10}" y="{y+4:.1f}" text-anchor="end">{gv}%</text>')
    for gv in [64, 66, 68, 70, 72, 74, 76]:
        x = sx(gv)
        p.append(f'<line class="grid" x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H-B}"/>')
        p.append(f'<text class="tick" x="{x:.1f}" y="{H-B+18}" text-anchor="middle">{gv}%</text>')

    p.append(f'<line class="axis" x1="{L}" y1="{H-B}" x2="{W-R}" y2="{H-B}"/>')
    p.append(f'<line class="axis" x1="{L}" y1="{T}" x2="{L}" y2="{H-B}"/>')
    p.append(f'<text class="lbl" x="{(L+W-R)/2}" y="{H-B+40}" text-anchor="middle">'
             f'graded success →</text>')
    p.append(f'<text class="lbl" x="18" y="{(T+H-B)/2}" text-anchor="middle" '
             f'transform="rotate(-90 18 {(T+H-B)/2})">← harm rate (share of runs)</text>')

    # The two corners the story is about, called out as quiet annotations
    # rather than as a second encoding.
    p.append(f'<text class="note" x="{W-R-6}" y="{T+14}" text-anchor="end">'
             f'accurate and destructive ↗</text>')
    p.append(f'<text class="note" x="{L+8}" y="{H-B-10}">safest ↙</text>')

    # Hand-placed so no two label blocks overlap; each is (dx, dy) from its dot,
    # and a negative dy lifts a label above a dot sitting on the floor.
    nudge = {"B1-auth": (13, 4), "A1": (13, 4), "D2-auth": (-13, -6),
             "D1": (13, 6), "C1": (13, 4), "A2": (13, 4), "B2-auth": (13, -14)}
    anchor = {"D2-auth": "end"}
    for arm, succ, harm in pts:
        cx, cy = sx(succ), sy(harm)
        hero = arm in ("B2-auth", "C1")
        cls = "s1" if hero else "s2"
        rad = 7 if hero else 5.5
        p.append(f'<circle class="{cls} ring" cx="{cx:.1f}" cy="{cy:.1f}" r="{rad}"/>')
        dx, dy = nudge.get(arm, (13, 4))
        ta = anchor.get(arm, "start")
        lc = "lbl-strong" if hero else "lbl"
        p.append(f'<text class="{lc}" x="{cx+dx:.1f}" y="{cy+dy:.1f}" '
                 f'text-anchor="{ta}">{esc(arm)}</text>')
        # Both axes are already named; repeating "harm" in every label widened
        # the blocks enough to collide.
        p.append(f'<text class="note" x="{cx+dx:.1f}" y="{cy+dy+14:.1f}" '
                 f'text-anchor="{ta}">{succ:.1f}% · {harm:.2f}%</text>')

    p.append(f'<text class="note" x="24" y="{H-38}">'
             f'The four arms above 71% sit within 2.9 pp of each other — under '
             f'this run’s 7.1 pp floor.</text>')
    p.append(f'<text class="note" x="24" y="{H-20}">'
             f'Horizontally they are tied. Vertically they span a factor of '
             f'sixty.</text>')
    write(out / "safety-accuracy.svg", p)


# ---- 2 · skill effect dumbbell -------------------------------------------

def chart_skill_effect(A: Path, out: Path) -> None:
    """Change between two states → dumbbell. A grouped bar muddles direction."""
    rows = read_csv(A, "skill_effect.csv")
    W, H = 760, 400
    p = svg_open(W, H, "What a hand-written skill actually buys",
                 "Same skill file, three packagings · before → after")

    panels = [
        ("abstention (share of unanswerable tasks declined)",
         [(r["pair"], f(r, "abstain_before") * 100, f(r, "abstain_after") * 100)
          for r in rows], "%", 60.0, 102.0),
        ("fabricated answers (count, of 180 unanswerable)",
         [(r["pair"], f(r, "fp_before"), f(r, "fp_after")) for r in rows],
         "", 0.0, 55.0),
    ]

    PL, PW = 210, 210
    for pi, (cap, data, unit, lo, hi) in enumerate(panels):
        px = PL + pi * (PW + 96)
        p.append(f'<text class="lbl" x="{px}" y="88">{esc(cap.split(" (")[0])}</text>')
        p.append(f'<text class="note" x="{px}" y="103">'
                 f'{esc(cap.split("(")[1][:-1])}</text>')

        def sx(v, px=px, lo=lo, hi=hi):
            return px + (v - lo) / (hi - lo) * PW

        for i, (pair, before, after) in enumerate(data):
            y = 150 + i * 62
            if pi == 0:
                p.append(f'<text class="lbl-strong" x="24" y="{y+4}">{esc(pair)}</text>')
            p.append(f'<line class="axis" x1="{px}" y1="{y+22}" x2="{px+PW}" y2="{y+22}"/>')
            xb, xa = sx(before), sx(after)
            p.append(f'<line x1="{xb:.1f}" y1="{y}" x2="{xa:.1f}" y2="{y}" '
                     f'stroke="var(--axis)" stroke-width="2"/>')
            p.append(f'<circle class="s2 ring" cx="{xb:.1f}" cy="{y}" r="6"/>')
            p.append(f'<circle class="s1 ring" cx="{xa:.1f}" cy="{y}" r="6"/>')
            # Emphasis follows the *after* state, not the larger number —
            # abstention rises and fabrication falls, and bolding by magnitude
            # would put the weight on "before" in the panel that improves.
            fmt = (lambda v: f"{v:.0f}{unit}") if unit else (lambda v: f"{v:.0f}")
            left_is_after = xa < xb
            p.append(f'<text class="{"lbl-strong" if left_is_after else "note"}" '
                     f'x="{min(xa,xb)-10:.1f}" y="{y+4}" text-anchor="end">'
                     f'{fmt(after if left_is_after else before)}</text>')
            p.append(f'<text class="{"note" if left_is_after else "lbl-strong"}" '
                     f'x="{max(xa,xb)+10:.1f}" y="{y+4}">'
                     f'{fmt(before if left_is_after else after)}</text>')

    # Legend — identity is never color-alone, so the swatches carry text.
    p.append(f'<circle class="s2 ring" cx="{PL+6}" cy="{H-52}" r="6"/>')
    p.append(f'<text class="lbl" x="{PL+20}" y="{H-48}">bare</text>')
    p.append(f'<circle class="s1 ring" cx="{PL+90}" cy="{H-52}" r="6"/>')
    p.append(f'<text class="lbl" x="{PL+104}" y="{H-48}">+ authored skill</text>')
    p.append(f'<text class="note" x="24" y="{H-38}">'
             f'Abstention moves the same way on every packaging, and fabrication '
             f'collapses on all three.</text>')
    p.append(f'<text class="note" x="24" y="{H-20}">'
             f'Success does not — only A2→B2-auth (+8.9 pp) clears the 7.1 pp '
             f'floor.</text>')
    write(out / "skill-effect.svg", p)


# ---- 3 · dimension heatmap -----------------------------------------------

def chart_dimension_heatmap(A: Path, out: Path) -> None:
    """Magnitude across a grid → sequential single hue, light→dark."""
    grid = read_csv(A, "verdict_grid.csv")
    dims = [("success_norm", "success"), ("harm_norm", "harm"),
            ("abstention_norm", "abstention"), ("cost_norm", "cost"),
            ("time_norm", "time")]
    rows = sorted(grid, key=lambda r: -f(r, "score"))

    W, H = 760, 452
    CW, CH, L, T = 108, 34, 116, 116
    # Four distinct arms hold the five column leads (B2-auth takes both harm and
    # abstention) — the title states the count rather than implying five.
    p = svg_open(W, H, "Five dimensions, four different leaders",
                 "Normalised 0–1 score per dimension · darker is better · "
                 "ranked by weighted composite")

    for j, (_, cap) in enumerate(dims):
        x = L + j * CW + CW / 2
        p.append(f'<text class="lbl" x="{x}" y="{T-14}" text-anchor="middle">{esc(cap)}</text>')
    p.append(f'<text class="note" x="{L-12}" y="{T-34}" text-anchor="end">weights</text>')
    for j, w in enumerate(["0.35", "0.25", "0.15", "0.15", "0.10"]):
        p.append(f'<text class="note" x="{L + j*CW + CW/2}" y="{T-34}" '
                 f'text-anchor="middle">{w}</text>')

    for i, r in enumerate(rows):
        y = T + i * CH
        p.append(f'<text class="lbl-strong" x="{L-12}" y="{y+22}" text-anchor="end">'
                 f'{esc(r["arm"])}</text>')
        p.append(f'<text class="note" x="{W-36}" y="{y+22}" text-anchor="end">'
                 f'{f(r,"score"):.2f}</text>')
        col_max = {}
        for key, _ in dims:
            col_max[key] = max(f(x, key) for x in rows)
        for j, (key, _) in enumerate(dims):
            v = f(r, key)
            fill = RAMP[min(len(RAMP) - 1, int(v * (len(RAMP) - 1)))]
            x = L + j * CW
            # 2px surface gap between cells — never a border around marks.
            p.append(f'<rect x="{x+1}" y="{y+1}" width="{CW-2}" height="{CH-2}" '
                     f'rx="3" fill="{fill}"/>')
            best = abs(v - col_max[key]) < 1e-9
            # Cell ink is chosen against the cell fill, not the surface, so it
            # must stay literal rather than take a theme token. Font comes from
            # the root <svg> rule — inlining it here would embed double quotes
            # inside an attribute and break the XML.
            ink = "#ffffff" if v > 0.62 else "#0b0b0b"
            weight = "600" if best else "400"
            p.append(f'<text x="{x+CW/2}" y="{y+CH/2+4}" text-anchor="middle" '
                     f'font-size="11.5" font-weight="{weight}" fill="{ink}">'
                     f'{v:.2f}</text>')

    # Kept under ~120 characters a line: SVG text does not wrap, so anything
    # wider than the viewBox is silently clipped at the right edge.
    p.append(f'<text class="note" x="24" y="{H-46}">'
             f'B2-auth wins the composite while placing fourth on success, the '
             f'heaviest-weighted dimension.</text>')
    p.append(f'<text class="note" x="24" y="{H-30}">'
             f'Change the weights and the winner changes — the score is a '
             f'preference, not a discovery.</text>')
    p.append(f'<text class="note" x="24" y="{H-12}">'
             f'Cells are min–max normalised across packaging arms, so 1.00 means '
             f'“best in this run”, not “good”.</text>')
    write(out / "dimension-heatmap.svg", p)


# ---- 4 · clobbered fields -------------------------------------------------

def chart_harm_fields(A: Path, out: Path) -> None:
    """Part-of-whole, five slices, one dominant → pie with emphasis.

    Emphasis rather than five categorical hues: the message is "one field is
    most of it", and a value-ramp on nominal categories would double-encode.
    """
    rows = [r for r in read_csv(A, "harm_detail.csv") if r["what"].startswith("field: ")]
    data = [(r["what"].removeprefix("field: "), int(r["events"])) for r in rows]
    data.sort(key=lambda t: -t[1])
    total = sum(v for _, v in data)

    W, H = 760, 420
    cx, cy, rad = 250, 236, 128
    p = svg_open(W, H, "Two-thirds of all destruction lands on one field",
                 f"{total} state-mutation events across the whole matrix, by field")

    fills = ["var(--s1)", "var(--quiet1)", "var(--quiet2)", "var(--quiet3)", "var(--quiet4)"]
    ang = -math.pi / 2
    for i, (name, val) in enumerate(data):
        sweep = 2 * math.pi * val / total
        x1, y1 = cx + rad * math.cos(ang), cy + rad * math.sin(ang)
        ang2 = ang + sweep
        x2, y2 = cx + rad * math.cos(ang2), cy + rad * math.sin(ang2)
        large = 1 if sweep > math.pi else 0
        p.append(f'<path d="M {cx} {cy} L {x1:.2f} {y1:.2f} '
                 f'A {rad} {rad} 0 {large} 1 {x2:.2f} {y2:.2f} Z" '
                 f'fill="{fills[i]}" stroke="var(--surface)" stroke-width="2"/>')
        ang = ang2

    # Direct labels in a legend column — never a number on every slice edge.
    ly = 128
    for i, (name, val) in enumerate(data):
        pct = val / total * 100
        p.append(f'<rect x="470" y="{ly-11}" width="12" height="12" rx="3" fill="{fills[i]}"/>')
        cls = "lbl-strong" if i == 0 else "lbl"
        p.append(f'<text class="{cls}" x="492" y="{ly}">{esc(name)}</text>')
        p.append(f'<text class="{cls}" x="{W-30}" y="{ly}" text-anchor="end">'
                 f'{val} · {pct:.0f}%</text>')
        ly += 30

    p.append(f'<text class="note" x="470" y="{ly+12}">'
             f'Almost always a full-object replace where a patch</text>')
    p.append(f'<text class="note" x="470" y="{ly+28}">'
             f'was wanted — and the API returned 200 every time.</text>')
    p.append(f'<text class="note" x="24" y="{H-20}">'
             f'An API-design finding, not a packaging one: every arm found this '
             f'operation. Some just fired it more often.</text>')
    write(out / "harm-fields.svg", p)


# ---- 5 · flakiness --------------------------------------------------------

def chart_flakiness(A: Path, out: Path) -> None:
    """Magnitude across nominal categories → horizontal bars, one hue, sorted."""
    rows = [r for r in read_csv(A, "efficiency.csv") if r["arm"] not in CONTROLS]
    data = sorted(((r["arm"], f(r, "flaky_rate") * 100) for r in rows),
                  key=lambda t: -t[1])

    W, H = 760, 406
    L, T, BW = 116, 92, 470
    hi = 46.0
    p = svg_open(W, H, "One of these arms is four times less predictable",
                 "Share of tasks whose outcome changed across three repeats "
                 "at temperature 0")

    for gv in [0, 10, 20, 30, 40]:
        x = L + gv / hi * BW
        p.append(f'<line class="grid" x1="{x:.1f}" y1="{T-12}" x2="{x:.1f}" y2="{T+len(data)*34-8}"/>')
        p.append(f'<text class="tick" x="{x:.1f}" y="{T-20}" text-anchor="middle">{gv}%</text>')

    for i, (arm, v) in enumerate(data):
        y = T + i * 34
        w = v / hi * BW
        hero = i == 0 or i == len(data) - 1
        fill = "var(--s1)" if hero else "var(--quiet1)"
        p.append(f'<text class="{"lbl-strong" if hero else "lbl"}" x="{L-12}" '
                 f'y="{y+15}" text-anchor="end">{esc(arm)}</text>')
        p.append(f'<rect x="{L}" y="{y}" width="{w:.1f}" height="20" rx="4" fill="{fill}"/>')
        p.append(f'<text class="{"lbl-strong" if hero else "lbl"}" x="{L+w+10:.1f}" '
                 f'y="{y+15}">{v:.1f}%</text>')

    p.append(f'<line class="axis" x1="{L}" y1="{T+len(data)*34-8}" x2="{L+BW}" '
             f'y2="{T+len(data)*34-8}"/>')
    p.append(f'<text class="note" x="24" y="{H-44}">'
             f'A2 changed its answer on 44% of the tasks it was asked three times, '
             f'at temperature 0. C1 did so on 11%.</text>')
    p.append(f'<text class="note" x="24" y="{H-24}">'
             f'A single-run benchmark would have reported one of those coin flips '
             f'as a finding.</text>')
    write(out / "flakiness.svg", p)


# ---- 6 · token efficiency -------------------------------------------------

def chart_token_efficiency(A: Path, out: Path) -> None:
    """Relationship on a ratio spanning an order of magnitude → log-x scatter.

    Deliberately priced in tokens, not dollars: a price card ages, a token
    count does not.
    """
    eff = {r["arm"]: r for r in read_csv(A, "efficiency.csv")}
    grid = read_csv(A, "verdict_grid.csv")
    pts = [(r["arm"], f(eff[r["arm"]], "ktokens_per_success"), f(r, "success_raw") * 100)
           for r in grid if r["arm"] in eff and r["arm"] not in CONTROLS]

    W, H = 760, 540
    L, R, T, B = 74, 200, 78, 92
    lx0, lx1 = math.log10(25), math.log10(220)
    y0, y1 = 63.0, 77.0

    def sx(v): return L + (math.log10(v) - lx0) / (lx1 - lx0) * (W - L - R)
    def sy(v): return H - B - (v - y0) / (y1 - y0) * (H - B - T)

    # D1 vs A1 is the honest "same accuracy" pair: 2.6 pp apart, under the
    # 7.1 pp floor. D1 vs A2 is 8.2 pp and *clears* it, so that pair is a real
    # accuracy gap and must not be captioned as a tie.
    p = svg_open(W, H, "Same accuracy, four times the tokens",
                 "Thousands of input tokens per successful task (log scale) "
                 "against graded success")

    for gv in [30, 50, 100, 200]:
        x = sx(gv)
        p.append(f'<line class="grid" x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H-B}"/>')
        p.append(f'<text class="tick" x="{x:.1f}" y="{H-B+18}" text-anchor="middle">{gv}k</text>')
    for gv in [64, 68, 72, 76]:
        y = sy(gv)
        p.append(f'<line class="grid" x1="{L}" y1="{y:.1f}" x2="{W-R}" y2="{y:.1f}"/>')
        p.append(f'<text class="tick" x="{L-10}" y="{y+4:.1f}" text-anchor="end">{gv}%</text>')

    p.append(f'<line class="axis" x1="{L}" y1="{H-B}" x2="{W-R}" y2="{H-B}"/>')
    p.append(f'<line class="axis" x1="{L}" y1="{T}" x2="{L}" y2="{H-B}"/>')
    p.append(f'<text class="lbl" x="{(L+W-R)/2}" y="{H-B+40}" text-anchor="middle">'
             f'input ktokens per success → (log)</text>')
    p.append(f'<text class="lbl" x="18" y="{(T+H-B)/2}" text-anchor="middle" '
             f'transform="rotate(-90 18 {(T+H-B)/2})">graded success</text>')

    # B1-auth labels left so its block clears B2-auth's, which sits 12k to its
    # right at almost the same height.
    anchor = {"B1-auth": "end"}
    for arm, kt, succ in pts:
        cx, cy = sx(kt), sy(succ)
        hero = arm in ("A1", "D1")
        ta = anchor.get(arm, "start")
        dx = -12 if ta == "end" else 12
        p.append(f'<circle class="{"s1" if hero else "s2"} ring" cx="{cx:.1f}" '
                 f'cy="{cy:.1f}" r="{7 if hero else 5.5}"/>')
        p.append(f'<text class="{"lbl-strong" if hero else "lbl"}" x="{cx+dx:.1f}" '
                 f'y="{cy+4:.1f}" text-anchor="{ta}">{esc(arm)}</text>')
        p.append(f'<text class="note" x="{cx+dx:.1f}" y="{cy+18:.1f}" '
                 f'text-anchor="{ta}">{kt:.0f}k</text>')

    p.append(f'<text class="note" x="24" y="{H-35}">'
             f'D1 and A1 are 2.6 pp apart on success — a tie under this run’s '
             f'7.1 pp floor — and 90k tokens apart per success.</text>')
    p.append(f'<text class="note" x="24" y="{H-14}">'
             f'A2 is the exception: 8.2 pp below D1, the one accuracy gap here '
             f'that clears the floor, and it spends 6.5× the tokens to get there.</text>')
    write(out / "token-efficiency.svg", p)


# ---- 7 · latency tail -----------------------------------------------------

def chart_latency(A: Path, out: Path) -> None:
    """NOT a box plot: efficiency.csv carries p50/p95/p99/max but no quartiles,
    so a box would invent an IQR. A percentile range strip states what is there.
    """
    rows = [r for r in read_csv(A, "efficiency.csv") if r["arm"] not in CONTROLS or r["arm"] == "Z-cheat"]
    data = sorted(((r["arm"], f(r, "p50_secs"), f(r, "p95_secs"), f(r, "p99_secs"))
                   for r in rows), key=lambda t: t[1])

    W, H = 760, 462
    L, T, BW = 116, 96, 470
    hi = 95.0
    p = svg_open(W, H, "The tail is where the packaging shows",
                 "Wall-clock per run · p50 dot, bar to p95, tick at p99")

    for gv in [0, 20, 40, 60, 80]:
        x = L + gv / hi * BW
        p.append(f'<line class="grid" x1="{x:.1f}" y1="{T-14}" x2="{x:.1f}" y2="{T+len(data)*34-10}"/>')
        p.append(f'<text class="tick" x="{x:.1f}" y="{T-22}" text-anchor="middle">{gv}s</text>')

    for i, (arm, p50, p95, p99) in enumerate(data):
        y = T + i * 34
        hero = arm == "Z-cheat"
        col = "var(--s1)" if hero else "var(--quiet1)"
        x50, x95, x99 = (L + v / hi * BW for v in (p50, p95, p99))
        p.append(f'<text class="{"lbl-strong" if hero else "lbl"}" x="{L-12}" '
                 f'y="{y+15}" text-anchor="end">{esc(arm)}</text>')
        p.append(f'<rect x="{x50:.1f}" y="{y+4}" width="{max(2,x95-x50):.1f}" '
                 f'height="12" rx="3" fill="{col}"/>')
        p.append(f'<line x1="{x99:.1f}" y1="{y+1}" x2="{x99:.1f}" y2="{y+19}" '
                 f'stroke="var(--axis)" stroke-width="2"/>')
        p.append(f'<circle cx="{x50:.1f}" cy="{y+10}" r="5" fill="var(--s2)" class="ring"/>')
        p.append(f'<text class="note" x="{x99+10:.1f}" y="{y+14}">'
                 f'{p50:.0f} → {p95:.0f} → {p99:.0f}s</text>')

    p.append(f'<circle cx="{L+6}" cy="{H-62}" r="5" fill="var(--s2)" class="ring"/>')
    p.append(f'<text class="lbl" x="{L+20}" y="{H-58}">p50</text>')
    p.append(f'<rect x="{L+66}" y="{H-68}" width="26" height="12" rx="3" fill="var(--quiet1)"/>')
    p.append(f'<text class="lbl" x="{L+100}" y="{H-58}">p50–p95</text>')
    p.append(f'<line x1="{L+180}" y1="{H-71}" x2="{L+180}" y2="{H-53}" stroke="var(--axis)" stroke-width="2"/>')
    p.append(f'<text class="lbl" x="{L+190}" y="{H-58}">p99</text>')
    p.append(f'<text class="note" x="24" y="{H-30}">'
             f'Z-cheat’s p95 is 69s against C1’s 41s on the same shell — the cost '
             f'of stopping to read a file it was told about.</text>')
    p.append(f'<text class="note" x="24" y="{H-12}">'
             f'No quartiles are stored, so this is a percentile strip rather than '
             f'a box plot — an IQR here would be invented.</text>')
    write(out / "latency-tail.svg", p)


# ---- 8 · per-core difficulty ---------------------------------------------

def chart_core_difficulty(A: Path, out: Path) -> None:
    """Distribution of a single measure → histogram. Grades the task suite."""
    rows = read_csv(A, "cores.csv")
    answerable = [f(r, "success_rate") * 100 for r in rows
                  if not r["core_id"].endswith("-unanswerable")]
    unans = [f(r, "success_rate") * 100 for r in rows
             if r["core_id"].endswith("-unanswerable")]

    bins = list(range(0, 101, 10))
    def hist(vals):
        h = [0] * (len(bins) - 1)
        for v in vals:
            k = min(int(v // 10), len(h) - 1)
            h[k] += 1
        return h
    ha, hu = hist(answerable), hist(unans)
    top = max(max(ha), max(hu)) + 2

    W, H = 760, 414
    L, T, PH, PW = 74, 96, 200, 600
    p = svg_open(W, H, "The suite has a floor and a ceiling",
                 f"Per-core success across all ten arms · "
                 f"{len(answerable)} answerable cores, {len(unans)} unanswerable")

    bw = PW / (len(bins) - 1)
    for gv in range(0, top + 1, 5):
        y = T + PH - gv / top * PH
        p.append(f'<line class="grid" x1="{L}" y1="{y:.1f}" x2="{L+PW}" y2="{y:.1f}"/>')
        p.append(f'<text class="tick" x="{L-10}" y="{y+4:.1f}" text-anchor="end">{gv}</text>')

    for i in range(len(bins) - 1):
        x = L + i * bw
        for vals, col, off in ((ha, "var(--s1)", 0), (hu, "var(--s2)", bw / 2)):
            v = vals[i]
            if not v:
                continue
            h = v / top * PH
            p.append(f'<rect x="{x+off+2:.1f}" y="{T+PH-h:.1f}" width="{bw/2-4:.1f}" '
                     f'height="{h:.1f}" rx="3" fill="{col}"/>')
        p.append(f'<text class="tick" x="{x+bw/2:.1f}" y="{T+PH+18}" '
                 f'text-anchor="middle">{bins[i]}–{bins[i+1]}</text>')

    p.append(f'<line class="axis" x1="{L}" y1="{T+PH}" x2="{L+PW}" y2="{T+PH}"/>')
    p.append(f'<text class="lbl" x="{L+PW/2}" y="{T+PH+40}" text-anchor="middle">'
             f'success rate across all arms (%)</text>')
    p.append(f'<text class="lbl" x="20" y="{T+PH/2}" text-anchor="middle" '
             f'transform="rotate(-90 20 {T+PH/2})">cores</text>')

    p.append(f'<rect x="{L}" y="{H-52}" width="12" height="12" rx="3" fill="var(--s1)"/>')
    p.append(f'<text class="lbl" x="{L+20}" y="{H-42}">answerable cores</text>')
    p.append(f'<rect x="{L+170}" y="{H-52}" width="12" height="12" rx="3" fill="var(--s2)"/>')
    p.append(f'<text class="lbl" x="{L+190}" y="{H-42}">unanswerable cores</text>')
    p.append(f'<text class="note" x="24" y="{H-24}">'
             f'The cluster at 10–20% is 17 cores nearly every arm failed; the '
             f'spread above 60% is unanswerable cores nearly every arm declined.</text>')
    p.append(f'<text class="note" x="24" y="{H-8}">'
             f'Both are suite-pruning signals, not packaging results.</text>')
    write(out / "core-difficulty.svg", p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="results/baseline-experiment-80")
    ap.add_argument("--out", default=None,
                    help="defaults to <run>/charts/article")
    args = ap.parse_args()

    run = Path(args.run)
    A = run / "analysis"
    out = Path(args.out) if args.out else run / "charts" / "article"
    out.mkdir(parents=True, exist_ok=True)

    chart_safety_accuracy(A, out)
    chart_skill_effect(A, out)
    chart_dimension_heatmap(A, out)
    chart_harm_fields(A, out)
    chart_flakiness(A, out)
    chart_token_efficiency(A, out)
    chart_latency(A, out)
    chart_core_difficulty(A, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
