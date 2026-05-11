"""Tests for api.services.programmatic_audit (pure shingle/pattern analysis)."""

from __future__ import annotations

from dataclasses import dataclass

from api.services.programmatic_audit import (
    _group_by_pattern,
    _shingles,
    _words,
    analyze_pages,
)


@dataclass
class FakePage:
    url: str
    textSnippet: str
    wordCount: int


_BOILERPLATE = (
    "Notre entreprise de plomberie intervient rapidement pour tous vos travaux "
    "de plomberie et de chauffage a domicile sept jours sur sept avec un devis "
    "gratuit et sans engagement par des artisans qualifies dans la ville de"
)


def _city_page(city: str) -> FakePage:
    # Identical boilerplate, only the trailing city name changes -> very low
    # per-page uniqueness once shingled.
    snippet = f"{_BOILERPLATE} {city}"
    return FakePage(url=f"https://exemple.com/services/plomberie/{city}", textSnippet=snippet, wordCount=180)


def test_words_and_shingles_helpers():
    assert _words("Hello, MONDE 42!") == ["hello", "monde", "42"]
    # Accented chars are kept.
    assert "déménagement" in _words("Le déménagement parisien")
    sh = _shingles(["a", "b", "c", "d", "e"], n=4)
    assert sh == {"a b c d", "b c d e"}
    # Fewer than n words -> the words themselves.
    assert _shingles(["a", "b"], n=4) == {"a", "b"}


def test_group_by_pattern_finds_templated_group():
    paths = [
        "/services/plomberie/lyon",
        "/services/plomberie/paris",
        "/services/plomberie/marseille",
        "/services/plomberie/lille",
        "/services/plomberie/nantes",
        "/a-propos",
        "/contact",
    ]
    groups = _group_by_pattern(paths)
    assert groups, "expected at least one templated group"
    # The city group must be detected and use a {} placeholder.
    matching = [pat for pat, members in groups.items() if len(members) >= 5 and "{}" in pat]
    assert matching
    pat = matching[0]
    assert "{}" in pat
    assert pat.startswith("/services/plomberie")


def test_programmatic_site_detected():
    pages = [_city_page(c) for c in ("lyon", "paris", "marseille", "lille", "nantes", "rennes")]
    result = analyze_pages(pages)
    assert result["isProgrammatic"] is True
    assert result["groups"]
    g = result["groups"][0]
    assert "{}" in g["pattern"]
    assert g["pageCount"] >= 6
    # Snippets are quasi-identical -> low uniqueness, gated.
    assert g["uniquenessRatio"] < 0.5
    assert g["gate"] in ("WARNING", "HARD_STOP")
    assert g["notes"]


def test_non_programmatic_site():
    pages = [
        FakePage(
            url="https://exemple.com/",
            textSnippet="Bienvenue sur le site de notre agence creative basee a Bordeaux",
            wordCount=400,
        ),
        FakePage(
            url="https://exemple.com/a-propos",
            textSnippet="Notre histoire commence en 2012 avec une equipe de trois passionnes",
            wordCount=600,
        ),
        FakePage(
            url="https://exemple.com/blog/seo-2026",
            textSnippet="Les tendances SEO de 2026 selon nos experts en referencement naturel",
            wordCount=1200,
        ),
    ]
    result = analyze_pages(pages)
    assert result["isProgrammatic"] is False
    assert result["groups"] == []


def test_empty_pages():
    assert analyze_pages([]) == {"isProgrammatic": False, "groups": []}
