"""Chart primitives, hand-rolled.

No plotting dependency: these emit `<svg>` strings that inline into the HTML and
also stand alone as files, so a chart diffs in git and renders headless.

Colour comes from the validated categorical palette (dataviz `references/
palette.md`), assigned in fixed slot order and never cycled. Every chart is
written against CSS custom properties, so light and dark are two selected sets
of steps rather than an automatic inversion.

The light-mode steps for slots 3, 4 and 5 sit below 3:1 on the light surface, so
the relief rule applies throughout: every chart here ships visible labels, and
the page carries a table view.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Sequence

#: Categorical slots, in the order the validator passed. Never reordered,
#: never cycled — a ninth series folds into "other" instead.
SERIES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                "#e87ba4", "#008300", "#4a3aa7", "#e34948")
SERIES_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500",
               "#d55181", "#008300", "#9085e9", "#e66767")

#: Single blue hue, light to dark. Sequential encoding only.
SEQUENTIAL = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
              "#256abf", "#184f95", "#0d366b")

#: Outcome quality, worst to best. An ORDINAL ramp, not categorical: these are
#: ordered states, and the six-colour categorical set hard-failed all-pairs CVD
#: (orange vs green, ΔE 3.2 protan) — a pair that genuinely appears side by side
#: whenever an intermediate segment is zero.
ORDINAL_LIGHT = ("#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281", "#0a2f5c")
ORDINAL_DARK = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#184f95", "#0d3a6e")

#: Truncation is not a grade — it is the absence of one. Carried by texture and
#: a neutral fill rather than a position on the quality ramp, so it can never be
#: misread as "slightly worse than a wrong answer".
NEUTRAL = "outcome-neutral"

#: Fixed, never themed, never reused as a series colour.
STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}


def palette_css() -> str:
    """Custom properties for both modes.

    Dark values are declared under the media query *and* the `data-theme` scope
    so a viewer's explicit toggle wins in both directions.
    """
    light = "\n".join(f"    --series-{i + 1}: {c};"
                      for i, c in enumerate(SERIES_LIGHT))
    dark = "\n".join(f"    --series-{i + 1}: {c};"
                     for i, c in enumerate(SERIES_DARK))
    seq_light = "\n".join(f"    --seq-{i + 1}: {c};"
                          for i, c in enumerate(SEQUENTIAL))
    seq_dark = "\n".join(f"    --seq-{i + 1}: {c};"
                         for i, c in enumerate(reversed(SEQUENTIAL)))
    ord_light = "\n".join(f"    --ord-{i + 1}: {c};"
                          for i, c in enumerate(ORDINAL_LIGHT))
    ord_dark = "\n".join(f"    --ord-{i + 1}: {c};"
                         for i, c in enumerate(ORDINAL_DARK))
    status = "\n".join(f"    --status-{k}: {v};" for k, v in STATUS.items())
    return f""".viz {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #78776f;
    --grid: #e6e5e1;
    --band: #ecebe7;
{light}
{seq_light}
{ord_light}
{status}
    --neutral: #b8b7b0;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz {{
      color-scheme: dark;
      --surface-1: #1a1a19;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #8f8e85;
      --grid: #333331;
      --band: #2a2a28;
{dark}
{seq_dark}
{ord_dark}
      --neutral: #56554f;
    }}
  }}
  :root[data-theme="dark"] .viz {{
    color-scheme: dark;
    --surface-1: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #8f8e85;
    --grid: #333331;
    --band: #2a2a28;
{dark}
{seq_dark}
{ord_dark}
    --neutral: #56554f;
  }}"""


def _e(text: object) -> str:
    return escape(str(text), quote=True)


@dataclass(frozen=True, slots=True)
class Bar:
    label: str
    value: float | None
    #: Wilson interval, drawn as a whisker.
    ci: tuple[float, float] | None = None
    #: Below the minimum detectable effect — rendered hatched and greyed.
    muted: bool = False
    note: str = ""
    slot: int = 1


def _svg(width: int, height: int, body: str, title: str) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMinYMin meet" role="img" '
        f'aria-label="{_e(title)}" xmlns="http://www.w3.org/2000/svg" '
        f'style="max-width:{width}px">'
        f"<title>{_e(title)}</title>{body}</svg>"
    )


def _hatch_defs() -> str:
    """Texture for below-MDE bars: the CVD/print/forced-colors fallback, and
    here also the 'not a finding' signal, so it never rests on colour alone."""
    return (
        '<defs><pattern id="hatch" width="6" height="6" '
        'patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
        '<rect width="6" height="6" fill="var(--band)"/>'
        '<line x1="0" y1="0" x2="0" y2="6" stroke="var(--text-muted)" '
        'stroke-width="2" opacity="0.5"/></pattern></defs>'
    )


def bar_chart(bars: Sequence[Bar], *, title: str, unit: str = "%",
              domain: tuple[float, float] | None = None,
              band: tuple[float, float] | None = None,
              width: int = 680, row_height: int = 34) -> str:
    """Horizontal bars with optional CI whiskers and a shaded MDE band."""
    if not bars:
        return _svg(width, 40, "", title)

    label_w, pad_r = 92, 74
    plot_w = width - label_w - pad_r
    height = len(bars) * row_height + 34

    values = [b.value for b in bars if b.value is not None]
    lo, hi = domain if domain else (min(values + [0.0]), max(values + [0.0]))
    if hi == lo:
        hi = lo + 1.0
    span = hi - lo

    def x(v: float) -> float:
        return label_w + (v - lo) / span * plot_w

    parts = [_hatch_defs()]

    if band:
        # Clamp to the plot area. An MDE wider than the data would otherwise
        # paint the whole chart grey and make every label unreadable — which is
        # a real risk at small n, exactly when the band matters most.
        bx0 = max(float(label_w), x(band[0]))
        bx1 = min(float(label_w + plot_w), x(band[1]))
        if bx1 > bx0:
            parts.append(
                f'<rect x="{bx0:.1f}" y="14" width="{bx1 - bx0:.1f}" '
                f'height="{len(bars) * row_height}" fill="var(--band)" '
                f'opacity="0.85"/>'
                f'<text x="{bx0 + 4:.1f}" y="11" font-size="9" '
                f'fill="var(--text-muted)">below MDE</text>'
            )

    if lo < 0 < hi:
        parts.append(f'<line x1="{x(0):.1f}" y1="14" x2="{x(0):.1f}" '
                     f'y2="{14 + len(bars) * row_height}" stroke="var(--grid)" '
                     f'stroke-width="1"/>')

    for i, bar in enumerate(bars):
        y = 14 + i * row_height
        cy = y + row_height / 2
        parts.append(
            f'<text x="{label_w - 8}" y="{cy + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="var(--text-secondary)">{_e(bar.label)}</text>'
        )
        if bar.value is None:
            parts.append(f'<text x="{label_w + 4}" y="{cy + 4:.1f}" font-size="10" '
                         f'fill="var(--text-muted)">no data</text>')
            continue

        x0, x1 = (x(min(0, bar.value)), x(max(0, bar.value)))
        fill = "url(#hatch)" if bar.muted else f"var(--series-{bar.slot})"
        parts.append(
            f'<rect x="{x0:.1f}" y="{y + 5:.1f}" width="{max(1.0, x1 - x0):.1f}" '
            f'height="{row_height - 12}" rx="4" fill="{fill}"/>'
        )
        if bar.ci:
            c0, c1 = x(bar.ci[0]), x(bar.ci[1])
            parts.append(
                f'<line x1="{c0:.1f}" y1="{cy:.1f}" x2="{c1:.1f}" y2="{cy:.1f}" '
                f'stroke="var(--text-muted)" stroke-width="2"/>'
                f'<line x1="{c0:.1f}" y1="{cy - 4:.1f}" x2="{c0:.1f}" '
                f'y2="{cy + 4:.1f}" stroke="var(--text-muted)" stroke-width="2"/>'
                f'<line x1="{c1:.1f}" y1="{cy - 4:.1f}" x2="{c1:.1f}" '
                f'y2="{cy + 4:.1f}" stroke="var(--text-muted)" stroke-width="2"/>'
            )
        # Direct label: mandatory relief for the sub-3:1 light steps.
        if unit in ("%", "pp"):
            shown = f"{bar.value:+.0f}{unit}" if unit == "pp" else f"{bar.value:.0f}{unit}"
        elif abs(bar.value) >= 100:
            shown = f"{bar.value:,.0f}"
        else:
            shown = f"{bar.value:,.2f}"
        parts.append(
            f'<text x="{x1 + 6:.1f}" y="{cy + 4:.1f}" font-size="11" '
            f'fill="var(--text-primary)">{_e(shown)}</text>'
        )
        if bar.note:
            # Below the value rather than beside it: at small n the note and the
            # band label were colliding on exactly the bars that carry it.
            parts.append(
                f'<text x="{x1 + 6:.1f}" y="{cy + 13:.1f}" font-size="8" '
                f'fill="var(--text-muted)">{_e(bar.note)}</text>'
            )
    return _svg(width, height, "".join(parts), title)


#: Ink for a label sitting ON a fill.
#:
#: The ordinal ramp runs light-to-dark in BOTH themes — ord-1 is the palest step
#: whether the page is light or dark. So the ink must be FIXED, not a theme
#: token: `--text-primary` flips to white in dark mode and would put white
#: numerals on the palest segment, which is the bug this replaces. Only the
#: neutral fill genuinely flips with the theme, so it keeps the token.
_ON_FILL_INK = {
    "var(--ord-1)": "#0b0b0b", "var(--ord-2)": "#0b0b0b",
    "var(--ord-3)": "#ffffff", "var(--ord-4)": "#ffffff",
    "var(--ord-5)": "#ffffff", "var(--ord-6)": "#ffffff",
    "var(--neutral)": "var(--text-primary)",
}


def _ink_on(fill: str) -> str:
    return _ON_FILL_INK.get(fill, "#ffffff")


def stacked_bars(labels: Sequence[str], segments: Sequence[str],
                 data: Sequence[Sequence[float]], *, title: str,
                 fills: Sequence[str] | None = None, show_total: bool = True,
                 width: int = 680, row_height: int = 30) -> str:
    """One row per label; segments in fixed slot order, 2px surface gaps."""
    if not labels:
        return _svg(width, 40, "", title)

    label_w, pad_r = 92, 46
    plot_w = width - label_w - pad_r
    height = len(labels) * row_height + 14
    totals = [sum(row) or 1 for row in data]

    parts = []
    for i, (label, row) in enumerate(zip(labels, data)):
        y = 14 + i * row_height
        parts.append(f'<text x="{label_w - 8}" y="{y + row_height / 2 + 4:.1f}" '
                     f'text-anchor="end" font-size="11" '
                     f'fill="var(--text-secondary)">{_e(label)}</text>')
        cursor = float(label_w)
        for slot, value in enumerate(row):
            if value <= 0:
                continue
            seg_w = value / totals[i] * plot_w
            fill = (fills[slot] if fills and slot < len(fills)
                    else f"var(--series-{slot + 1})")
            parts.append(
                f'<rect x="{cursor:.1f}" y="{y + 5:.1f}" '
                f'width="{max(1.0, seg_w - 2):.1f}" height="{row_height - 12}" '
                f'rx="2" fill="{fill}">'
                f"<title>{_e(segments[slot])}: {int(value)}</title></rect>"
            )
            if seg_w > 24:
                ink = _ink_on(fill)
                parts.append(
                    f'<text x="{cursor + seg_w / 2 - 1:.1f}" '
                    f'y="{y + row_height / 2 + 4:.1f}" text-anchor="middle" '
                    f'font-size="10" font-weight="600" fill="{ink}">'
                    f"{int(value)}</text>"
                )
            cursor += seg_w
        if show_total:
            # Only meaningful when segments are run counts. On a token stack
            # "n=1604" reads as 1604 runs, which is a different number entirely.
            parts.append(f'<text x="{width - pad_r + 6}" '
                         f'y="{y + row_height / 2 + 4:.1f}" font-size="10" '
                         f'fill="var(--text-muted)">n={int(totals[i])}</text>')
    return _svg(width, height, "".join(parts), title)


def grouped_bars(groups: Sequence[str], series: Sequence[str],
                 data: Sequence[Sequence[float | None]], *, title: str,
                 width: int = 680, group_height: int = 22) -> str:
    """One block per group, one bar per series. Values direct-labelled."""
    if not groups:
        return _svg(width, 40, "", title)

    label_w, pad_r = 92, 52
    plot_w = width - label_w - pad_r
    bar_h = max(9, group_height // max(1, len(series)))
    height = len(groups) * (bar_h * len(series) + 12) + 14

    parts, y = [], 14
    for gi, group in enumerate(groups):
        parts.append(f'<text x="{label_w - 8}" y="{y + bar_h * len(series) / 2 + 4:.1f}" '
                     f'text-anchor="end" font-size="11" '
                     f'fill="var(--text-secondary)">{_e(group)}</text>')
        for si, value in enumerate(data[gi]):
            by = y + si * bar_h
            if value is None:
                parts.append(f'<text x="{label_w + 4}" y="{by + bar_h - 1:.1f}" '
                             f'font-size="9" fill="var(--text-muted)">n/a</text>')
                continue
            w = max(1.0, value * plot_w)
            parts.append(
                f'<rect x="{label_w}" y="{by:.1f}" width="{w:.1f}" '
                f'height="{bar_h - 2}" rx="2" fill="var(--series-{si + 1})">'
                f"<title>{_e(series[si])}: {value:.0%}</title></rect>"
                f'<text x="{label_w + w + 5:.1f}" y="{by + bar_h - 3:.1f}" '
                f'font-size="9" fill="var(--text-primary)">{value:.0%}</text>'
            )
        y += bar_h * len(series) + 12
    return _svg(width, height, "".join(parts), title)


def scatter(points: Sequence[tuple[str, float, float]], *, title: str,
            x_label: str, y_label: str, width: int = 680,
            height: int = 300) -> str:
    """One labelled point per arm. Single hue — identity comes from the label,
    not from colour, which is what keeps this inside the all-pairs series cap."""
    if not points:
        return _svg(width, 60, "", title)

    pad_l, pad_b, pad_t, pad_r = 58, 38, 16, 90
    plot_w, plot_h = width - pad_l - pad_r, height - pad_b - pad_t

    xs = [p[1] for p in points]
    ys = [p[2] for p in points]
    x_lo, x_hi = min(xs + [0.0]), max(xs) or 1.0
    y_lo, y_hi = 0.0, max(ys + [1.0])
    if x_hi == x_lo:
        x_hi = x_lo + 1

    def px(v: float) -> float:
        return pad_l + (v - x_lo) / (x_hi - x_lo) * plot_w

    def py(v: float) -> float:
        return pad_t + plot_h - (v - y_lo) / (y_hi - y_lo) * plot_h

    parts = [
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + plot_h}" '
        f'stroke="var(--grid)"/>'
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" '
        f'y2="{pad_t + plot_h}" stroke="var(--grid)"/>'
        f'<text x="{pad_l + plot_w / 2}" y="{height - 6}" text-anchor="middle" '
        f'font-size="10" fill="var(--text-secondary)">{_e(x_label)}</text>'
        f'<text x="12" y="{pad_t + plot_h / 2}" font-size="10" '
        f'fill="var(--text-secondary)" transform="rotate(-90 12 '
        f'{pad_t + plot_h / 2})" text-anchor="middle">{_e(y_label)}</text>'
    ]
    for frac in (0.0, 0.5, 1.0):
        gy = py(y_lo + frac * (y_hi - y_lo))
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l + plot_w}" '
                     f'y2="{gy:.1f}" stroke="var(--grid)" stroke-dasharray="2 3"/>'
                     f'<text x="{pad_l - 6}" y="{gy + 3:.1f}" text-anchor="end" '
                     f'font-size="9" fill="var(--text-muted)">'
                     f'{(y_lo + frac * (y_hi - y_lo)):.0%}</text>')

    for label, xv, yv in points:
        cx, cy = px(xv), py(yv)
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" '
            f'fill="var(--series-1)" stroke="var(--surface-1)" stroke-width="2">'
            f"<title>{_e(label)}: {xv:,.4f} / {yv:.0%}</title></circle>"
            f'<text x="{cx + 10:.1f}" y="{cy + 4:.1f}" font-size="11" '
            f'fill="var(--text-primary)">{_e(label)}</text>'
        )
    return _svg(width, height, "".join(parts), title)


def heatmap(cells: Sequence[tuple[str, str, float, str]], rows: Sequence[str],
            cols: Sequence[str], *, title: str, width: int = 260) -> str:
    """A small confusion matrix. Sequential blue: one hue, light to dark."""
    cell_w, cell_h, pad_l, pad_t = 74, 42, 74, 22
    height = pad_t + len(rows) * cell_h + 8
    lookup = {(r, c): (v, text) for r, c, v, text in cells}
    peak = max([v for _, _, v, _ in cells] or [1]) or 1

    parts = []
    for ci, col in enumerate(cols):
        parts.append(f'<text x="{pad_l + ci * cell_w + cell_w / 2}" y="{pad_t - 7}" '
                     f'text-anchor="middle" font-size="10" '
                     f'fill="var(--text-secondary)">{_e(col)}</text>')
    for ri, row in enumerate(rows):
        y = pad_t + ri * cell_h
        parts.append(f'<text x="{pad_l - 8}" y="{y + cell_h / 2 + 4}" '
                     f'text-anchor="end" font-size="10" '
                     f'fill="var(--text-secondary)">{_e(row)}</text>')
        for ci, col in enumerate(cols):
            value, label = lookup.get((row, col), (0, ""))
            step = min(6, int(value / peak * 6)) if peak else 0
            # Fixed inks, same reasoning as _ON_FILL_INK: the sequential ramp
            # is light-to-dark in both themes, so a flipping token is wrong at
            # one end or the other.
            ink = "#ffffff" if step >= 4 else "#0b0b0b"
            parts.append(
                f'<rect x="{pad_l + ci * cell_w}" y="{y}" '
                f'width="{cell_w - 2}" height="{cell_h - 2}" rx="3" '
                f'fill="var(--seq-{step + 1})"/>'
                f'<text x="{pad_l + ci * cell_w + cell_w / 2 - 1}" '
                f'y="{y + cell_h / 2 + 1}" text-anchor="middle" font-size="13" '
                f'fill="{ink}">{int(value)}</text>'
                f'<text x="{pad_l + ci * cell_w + cell_w / 2 - 1}" '
                f'y="{y + cell_h / 2 + 13}" text-anchor="middle" font-size="8" '
                f'fill="{ink}" opacity="0.8">{_e(label)}</text>'
            )
    return _svg(width, height, "".join(parts), title)


def legend(items: Sequence[str], *, slots: Sequence[int] | None = None,
           fills: Sequence[str] | None = None) -> str:
    """Always present for two or more series, so identity is never colour-alone."""
    slots = slots or list(range(1, len(items) + 1))
    chips = []
    for i, name in enumerate(items):
        fill = (fills[i] if fills and i < len(fills)
                else f"var(--series-{slots[i]})")
        chips.append(f'<span class="chip"><i style="background:{fill}"></i>'
                     f"{_e(name)}</span>")
    return f'<div class="legend">{"".join(chips)}</div>'
