"""Detect Schema.org structured data on an HTML page.

Looks for:
- **JSON-LD**: `<script type="application/ld+json">` blocks (Google's preferred
  format, so we collect these first).
- **Microdata**: `itemscope` + `itemtype="https://schema.org/Type"`.
- **RDFa**: `typeof="schema:Type"` or `vocab="https://schema.org/"` + `typeof`.

Validates each detected type against the February 2026 status list:
- ACTIVE    — recommended (Organization, LocalBusiness, Product, …)
- RESTRICTED— only for some sites (FAQPage: gov/health only)
- DEPRECATED— Google retired the rich result (HowTo, SpecialAnnouncement, …)
- UNKNOWN   — not in the enum; passed through without verdict.

The returned list is **factual** (what is on the page) so the analyzer prompt
can rely on it instead of guessing from headings.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Iterable

from bs4 import BeautifulSoup

from api.models import DetectedSchema

logger = logging.getLogger(__name__)


# Status lists from the AgriciDaniel seo-schema skill (MIT), Feb 2026.
_ACTIVE_TYPES = frozenset({
    "Organization", "LocalBusiness", "SoftwareApplication", "WebApplication",
    "Product", "ProductGroup", "Offer", "Service",
    "Article", "BlogPosting", "NewsArticle",
    "Review", "AggregateRating",
    "BreadcrumbList", "WebSite", "WebPage",
    "Person", "ProfilePage", "ContactPage",
    "VideoObject", "ImageObject",
    "Event", "JobPosting", "Course", "DiscussionForumPosting",
    "BroadcastEvent", "Clip", "SeekToAction", "SoftwareSourceCode",
})

_RESTRICTED_TYPES = {
    "FAQPage": (
        "Rich results restreints aux sites gouvernement/santé "
        "depuis août 2023. À retirer si site commercial."
    ),
}

_DEPRECATED_TYPES = {
    "HowTo": "Rich results retirés en septembre 2023 — à retirer.",
    "SpecialAnnouncement": "Déprécié le 31 juillet 2025.",
    "CourseInfo": "Retiré des rich results en juin 2025.",
    "EstimatedSalary": "Retiré des rich results en juin 2025.",
    "LearningVideo": "Retiré des rich results en juin 2025.",
    "ClaimReview": "Retiré des rich results en juin 2025.",
    "VehicleListing": "Retiré des rich results en juin 2025.",
    "PracticeProblem": "Retiré des rich results fin 2025.",
    "Dataset": "Retiré des rich results fin 2025.",
}


def detect(html: str) -> list[DetectedSchema]:
    """Return every Schema.org entity present in `html`."""
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    detected: list[DetectedSchema] = []
    detected.extend(_detect_json_ld(soup))
    detected.extend(_detect_microdata(soup))
    detected.extend(_detect_rdfa(soup))
    return _dedupe(detected)


# ---------------------------------------------------------------------------
# JSON-LD


def _detect_json_ld(soup: BeautifulSoup) -> Iterable[DetectedSchema]:
    scripts = soup.find_all("script", attrs={"type": re.compile(r"^application/ld\+json", re.I)})
    for script in scripts:
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            yield DetectedSchema(
                type="(invalid JSON-LD)",
                format="json-ld",
                status="unknown",
                issues=["JSON invalide — le bloc ne peut pas être parsé."],
            )
            continue
        yield from _extract_types(data, fmt="json-ld")


def _extract_types(data: object, fmt: str) -> Iterable[DetectedSchema]:
    """Recursively walk a JSON-LD object and yield every `@type` found."""
    if isinstance(data, list):
        for item in data:
            yield from _extract_types(item, fmt)
        return
    if not isinstance(data, dict):
        return

    type_value = data.get("@type")
    if isinstance(type_value, str):
        yield _build(type_value, fmt, data)
    elif isinstance(type_value, list):
        for t in type_value:
            if isinstance(t, str):
                yield _build(t, fmt, data)

    # Graphs carry multiple entities
    graph = data.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _extract_types(item, fmt)


def _build(type_name: str, fmt: str, payload: dict) -> DetectedSchema:
    status, issues = _classify(type_name)
    # Basic validity checks for JSON-LD
    if fmt == "json-ld":
        ctx = payload.get("@context")
        if ctx is None:
            issues.append("@context manquant (attendu 'https://schema.org').")
        elif isinstance(ctx, str) and "schema.org" not in ctx:
            issues.append(f"@context inattendu : {ctx!r}.")
    return DetectedSchema(
        type=type_name,
        format=fmt,  # type: ignore[arg-type]
        status=status,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Microdata


def _detect_microdata(soup: BeautifulSoup) -> Iterable[DetectedSchema]:
    for el in soup.find_all(attrs={"itemscope": True}):
        item_type = el.get("itemtype")
        if not item_type:
            continue
        if isinstance(item_type, list):
            item_type = " ".join(item_type)
        for url in str(item_type).split():
            type_name = url.rstrip("/").split("/")[-1]
            if not type_name:
                continue
            status, issues = _classify(type_name)
            yield DetectedSchema(
                type=type_name,
                format="microdata",
                status=status,
                issues=issues,
            )


# ---------------------------------------------------------------------------
# RDFa


_RDFA_PREFIX_RE = re.compile(r"(?:^|\s)(?:schema:)?([A-Z][A-Za-z0-9]+)")


def _detect_rdfa(soup: BeautifulSoup) -> Iterable[DetectedSchema]:
    for el in soup.find_all(attrs={"typeof": True}):
        typeof_val = el.get("typeof")
        if not typeof_val:
            continue
        if isinstance(typeof_val, list):
            typeof_val = " ".join(typeof_val)
        for match in _RDFA_PREFIX_RE.findall(str(typeof_val)):
            status, issues = _classify(match)
            yield DetectedSchema(
                type=match,
                format="rdfa",
                status=status,
                issues=issues,
            )


# ---------------------------------------------------------------------------
# Helpers


def _classify(type_name: str) -> tuple[str, list[str]]:
    if type_name in _DEPRECATED_TYPES:
        return "deprecated", [_DEPRECATED_TYPES[type_name]]
    if type_name in _RESTRICTED_TYPES:
        return "restricted", [_RESTRICTED_TYPES[type_name]]
    if type_name in _ACTIVE_TYPES:
        return "active", []
    return "unknown", []


def _dedupe(items: list[DetectedSchema]) -> list[DetectedSchema]:
    """Collapse identical (type, format) pairs, merging issues."""
    index: dict[tuple[str, str], DetectedSchema] = {}
    for s in items:
        key = (s.type, s.format)
        if key in index:
            # Keep the richer record
            existing = index[key]
            existing_issues = set(existing.issues)
            for issue in s.issues:
                if issue not in existing_issues:
                    existing.issues.append(issue)
                    existing_issues.add(issue)
        else:
            index[key] = s
    return list(index.values())
