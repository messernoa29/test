"""Tests for api.services.geo_audit (pure citability scoring)."""

from __future__ import annotations

from api.services.geo_audit import _is_question, score_page, score_site_layer


def test_is_question():
    assert _is_question("Comment installer une pompe à chaleur ?") is True
    assert _is_question("Pourquoi choisir notre agence?") is True
    assert _is_question("How does it work") is True
    assert _is_question("Mon titre") is False
    assert _is_question("") is False
    assert _is_question("Nos services de plomberie") is False


def test_score_page_well_structured_is_high():
    score, strengths, weaknesses = score_page(
        word_count=800,
        headings=[
            "Comment fonctionne le service ?",
            "Pourquoi nous choisir ?",
            "Combien ça coûte ?",
            "Quels délais d'intervention ?",
        ],
        text_snippet=(
            "En 2025, 87 % de nos clients recommandent le service. "
            "Le délai moyen d'intervention est de 2 heures."
        ),
        schemas=["FAQPage"],
        rendered_with_playwright=False,
    )
    assert score >= 70
    assert strengths
    assert 0 <= score <= 100


def test_score_page_poor_is_low():
    score, strengths, weaknesses = score_page(
        word_count=80,
        headings=[],
        text_snippet="Bienvenue sur notre site.",
        schemas=[],
        rendered_with_playwright=True,
    )
    assert score < 40
    assert weaknesses
    # Should flag JS-rendering and the missing schema.
    joined = " ".join(weaknesses).lower()
    assert "client" in joined  # "rendu côté client (JS)"
    assert "schema" in joined


def test_score_site_layer_parses_robots_blocking_gptbot():
    strengths, weaknesses, status = score_site_layer(
        robots_txt="User-agent: GPTBot\nDisallow: /",
        has_llms_txt=False,
    )
    assert status["GPTBot"] == "blocked"
    # Other AI crawlers not mentioned in this robots.txt.
    assert status["PerplexityBot"] == "not mentioned"
    # llms.txt missing -> reported as a weakness.
    assert any("llms.txt" in w for w in weaknesses)
    # The blocked GPTBot must be surfaced as a weakness.
    assert any("GPTBot" in w for w in weaknesses)


def test_score_site_layer_clean_robots():
    strengths, weaknesses, status = score_site_layer(
        robots_txt="User-agent: *\nDisallow: /admin/",
        has_llms_txt=True,
    )
    # No AI crawler blocked at root.
    assert all(not v.startswith("blocked") for v in status.values())
    assert any("llms.txt" in s for s in strengths)
