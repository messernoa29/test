"""Programmatic SEO quality gates.

Sites that generate hundreds of near-identical pages from a template
(city pages, "service in {city}", store locators…) are exactly what
Google's Scaled Content Abuse policy (March 2024) targets. We detect
URL-pattern groups, estimate per-group content uniqueness vs shared
boilerplate, and flag groups that look like doorway pages.

Pure Python — uses crawl signals we already have (URL paths, text
snippets, word counts).

Gates (claude-seo's tiers):
  uniqueness ≥ 60%  → PASS
  40% ≤ uniqueness < 60%  → WARNING
  uniqueness < 40%  → HARD STOP (doorway / penalty risk)

Method adapted from AgriciDaniel/claude-seo (skills/seo-programmatic).
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

_PASS_THRESHOLD = 0.60
_WARNING_THRESHOLD = 0.40
_MIN_GROUP_SIZE = 4  # below this, not "programmatic" — skip
_SHINGLE_SIZE = 4


def _segments(path: str) -> list[str]:
    return [p for p in path.split("/") if p]


def _group_by_pattern(paths: list[str]) -> dict[str, list[str]]:
    """Two-pass: bucket paths by (prefix segments, depth), then within each
    bucket replace the segment position(s) that actually vary with {}.

    A bucket becomes a "pattern" only if it has ≥ MIN_GROUP_SIZE members.
    Returns {pattern_string: [path, ...]}."""
    # Pass 1: bucket by (depth, all-but-last-segment tuple) — the common case
    # is "/prefix/.../{var}".
    by_key: dict[tuple, list[str]] = {}
    for p in paths:
        segs = _segments(p)
        if len(segs) < 1:
            continue
        # Try several "which segment varies" hypotheses: last, second-to-last.
        for var_idx in (len(segs) - 1, len(segs) - 2):
            if var_idx < 0:
                continue
            skeleton = tuple(
                ("{}" if i == var_idx else s) for i, s in enumerate(segs)
            )
            by_key.setdefault((len(segs), skeleton), []).append(p)

    # Pass 2: keep buckets that are big enough; collapse to a pattern string.
    out: dict[str, list[str]] = {}
    seen_paths: set[str] = set()
    # Process larger buckets first so a path is attributed to its strongest group.
    for (depth, skeleton), members in sorted(by_key.items(), key=lambda kv: -len(kv[1])):
        members = [m for m in members if m not in seen_paths]
        if len(members) < _MIN_GROUP_SIZE:
            continue
        if "{}" not in skeleton:
            continue
        pattern = "/" + "/".join(skeleton)
        out[pattern] = members
        seen_paths.update(members)
    return out


_WORD_RE = re.compile(r"[a-zà-ÿ0-9]+", re.I)


def _words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def _shingles(words: list[str], n: int = _SHINGLE_SIZE) -> set[str]:
    if len(words) < n:
        return set(words)
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def analyze_pages(pages: list) -> dict:
    """`pages` is a list of objects with .url, .textSnippet, .wordCount.
    Returns a dict matching ProgrammaticAuditSummary."""
    if not pages:
        return {"isProgrammatic": False, "groups": []}

    by_path = {urlparse(p.url).path or "/": p for p in pages}
    pattern_to_paths = _group_by_pattern(list(by_path.keys()))

    groups_out = []
    for pat, member_paths in pattern_to_paths.items():
        members = [by_path[mp] for mp in member_paths if mp in by_path]
        if len(members) < _MIN_GROUP_SIZE:
            continue

        # Build shingle sets from each member's snippet (best signal we have).
        member_shingles = []
        for m in members:
            sh = _shingles(_words(m.textSnippet or ""))
            if sh:
                member_shingles.append(sh)
        if len(member_shingles) < 2:
            continue

        # Shared boilerplate = shingles present in (almost) every member.
        counter: Counter[str] = Counter()
        for sh in member_shingles:
            for s in sh:
                counter[s] += 1
        n = len(member_shingles)
        # A shingle counts as "boilerplate" if it appears in ≥ 80% of members.
        boilerplate = {s for s, c in counter.items() if c >= max(2, int(0.8 * n))}
        all_shingles = set(counter.keys())
        if not all_shingles:
            continue
        boilerplate_ratio = len(boilerplate) / len(all_shingles)
        uniqueness = round(1.0 - boilerplate_ratio, 3)

        # Swap test (crude): can we replace the variable token and have the
        # snippet still make sense? Approx: if uniqueness is very low AND
        # word counts are tightly clustered, treat as doorway-ish.
        wcs = [getattr(m, "wordCount", 0) or 0 for m in members]
        avg_wc = round(sum(wcs) / len(wcs)) if wcs else 0
        wc_spread = (max(wcs) - min(wcs)) if wcs else 0
        tightly_clustered = avg_wc > 0 and wc_spread < 0.15 * avg_wc

        if uniqueness >= _PASS_THRESHOLD:
            gate = "PASS"
        elif uniqueness >= _WARNING_THRESHOLD:
            gate = "WARNING"
        else:
            gate = "HARD_STOP"

        notes: list[str] = []
        notes.append(f"{int(boilerplate_ratio * 100)}% du contenu (échantillon) est partagé entre les pages du groupe")
        if tightly_clustered:
            notes.append("Longueurs de contenu très homogènes — forte présomption de template peu enrichi")
        if gate == "HARD_STOP":
            notes.append("Risque doorway pages / Scaled Content Abuse (Google, mars 2024) — chaque page doit apporter une valeur propre substantielle")
        elif gate == "WARNING":
            notes.append("À renforcer : ajouter du contenu local/spécifique unique sur chaque page (avis, FAQ, données, photos)")

        groups_out.append({
            "pattern": pat,
            "pageCount": len(members),
            "sampleUrls": [m.url for m in members[:6]],
            "uniquenessRatio": uniqueness,
            "boilerplateRatio": round(boilerplate_ratio, 3),
            "avgWordCount": avg_wc,
            "gate": gate,
            "notes": notes,
        })

    groups_out.sort(key=lambda g: g["uniquenessRatio"])
    return {
        "isProgrammatic": bool(groups_out),
        "groups": groups_out[:20],
    }
