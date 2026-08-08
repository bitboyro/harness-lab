"""Docs are contracts, so the citations have to resolve.

Code cites docs by anchor (`Contract: archive/reference/statistics.md#power-and-mde`).
Anchors were chosen over the section numbers this project used to cite because a
number drifts silently on every edit — a renamed heading breaks loudly here
instead of quietly pointing a reader at the wrong paragraph.

The reference contracts live under `archive/`, which is gitignored and does not
ship. That is a distribution decision, not a demotion: they are still the live
rationale the code cites. So these checks run in full for anyone holding the
research trail, and skip — never fail — for someone working from a checkout
that never had it. A missing internal doc is not a broken build for them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
REFERENCE = ROOT / "archive" / "reference"

#: Whether the internal contracts are present in this working copy.
HAVE_REFERENCE = REFERENCE.is_dir()
needs_reference = pytest.mark.skipif(
    not HAVE_REFERENCE, reason="archive/reference is internal and not distributed")

#: `Contract: docs/a.md#x, #y; archive/reference/b.md#z` — one prefix, several targets.
_CONTRACT = re.compile(r"Contract:\s*(.+)")
_DOC_PATH = r"(?:docs|archive)/[\w/\-.]+\.md"

#: Markdown links, minus external ones.
_LINK = re.compile(r"\[[^\]]*\]\((\.{1,2}/[^)\s]+)\)")


def _slugs(text: str) -> set[str]:
    """Every anchor a heading or an explicit tag makes reachable."""
    found = set()
    for line in text.splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            slug = re.sub(r"[^\w\s-]", "", title.lower())
            found.add("#" + re.sub(r"\s", "-", slug).strip("-"))
    found |= {"#" + m for m in re.findall(r'<a id="([\w\-]+)"', text)}
    return found


def _contract_citations() -> list[tuple[Path, str, str]]:
    """(source file, doc path, anchor) for every Contract: line under src/."""
    out = []
    for py in sorted((ROOT / "src").rglob("*.py")):
        for raw in py.read_text().splitlines():
            m = _CONTRACT.search(raw)
            if not m:
                continue
            current = None
            for chunk in re.split(r"[;,]", m.group(1)):
                chunk = chunk.strip()
                if not chunk:
                    continue
                path = re.match(rf"({_DOC_PATH})", chunk)
                if path:
                    current = path.group(1)
                anchor = re.search(r"(#[\w\-]+)", chunk)
                if current:
                    out.append((py, current, anchor.group(1) if anchor else ""))
    return out


CITATIONS = _contract_citations()


def test_there_are_citations_to_check() -> None:
    """Guards the parser: a regex that silently matches nothing passes."""
    assert len(CITATIONS) >= 30


@pytest.mark.parametrize(
    "source,doc,anchor", CITATIONS,
    ids=[f"{s.name}->{d}{a}" for s, d, a in CITATIONS])
def test_every_contract_citation_resolves(source: Path, doc: str, anchor: str) -> None:
    target = ROOT / doc
    if doc.startswith("archive/") and not HAVE_REFERENCE:
        pytest.skip("archive/reference is internal and not distributed")
    assert target.is_file(), f"{source.name} cites {doc}, which does not exist"
    if anchor:
        available = _slugs(target.read_text())
        assert anchor in available, (
            f"{source.name} cites {doc}{anchor}, but that heading is gone. "
            f"Anchors present: {sorted(available)}")


def test_no_dangling_links_between_docs() -> None:
    """A reader following a link inside docs/ must land somewhere."""
    broken = []
    for md in sorted(DOCS.rglob("*.md")):
        for href in _LINK.findall(md.read_text()):
            path, _, anchor = href.partition("#")
            target = (md.parent / path).resolve() if path else md
            if not target.is_file():
                broken.append(f"{md.relative_to(ROOT)} -> {href}")
                continue
            if anchor and ("#" + anchor) not in _slugs(target.read_text()):
                broken.append(f"{md.relative_to(ROOT)} -> {href} (no such anchor)")
    assert not broken, "dangling links:\n  " + "\n  ".join(broken)


@needs_reference
def test_the_decision_ids_the_code_cites_still_exist() -> None:
    """Decision IDs are an API.

    A path that resolves while the ID means something else is worse than a
    broken link, so the IDs are checked separately from the file.
    """
    decisions = (REFERENCE / "decisions.md").read_text()
    cited = set()
    for py in (ROOT / "src").rglob("*.py"):
        for raw in py.read_text().splitlines():
            if "Contract:" in raw:
                cited |= set(re.findall(r"\b([FGO]\d{1,2})\b", raw))

    assert cited, "no decision IDs found in any Contract: line"
    for ident in sorted(cited):
        # Framing/structural decisions are headings; the O-series open
        # questions are table rows. Both are stable ids.
        assert (re.search(rf"^### {ident} —", decisions, re.M)
                or re.search(rf"\*\*{ident}\*\*", decisions)), (
            f"code cites decision {ident}, which is no longer in decisions.md")
