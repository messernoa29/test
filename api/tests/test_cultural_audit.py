"""Tests for api.services.cultural_audit (pure locale/format heuristics)."""

from __future__ import annotations

from api.services.cultural_audit import _norm_lang, audit_page, detect_page_locale


def test_norm_lang():
    assert _norm_lang("fr-FR") == "fr"
    assert _norm_lang("FR") == "fr"
    assert _norm_lang("fr_CA") == "fr"
    assert _norm_lang("") == ""
    assert _norm_lang("de-DE") == "de"


def test_detect_page_locale_html_lang_priority():
    # html lang wins even if the URL path suggests another locale.
    assert detect_page_locale(html_lang="fr-FR", hreflang_self="", url="https://x.com/de/page") == "fr"


def test_detect_page_locale_falls_back_to_url_path():
    assert detect_page_locale(html_lang="", hreflang_self="", url="https://x.com/de/produkte") == "de"
    # Unknown everywhere -> empty.
    assert detect_page_locale(html_lang="", hreflang_self="", url="https://x.com/page") == ""


def test_audit_page_fr_with_anglo_signals():
    issues = audit_page(
        locale="fr",
        body_text=(
            "Découvrez notre offre à $49.00 par mois. "
            "Plus de 1,000.00 unités vendues cette année."
        ),
        cta_texts=["Buy now"],
    )
    text = " | ".join(issues).lower()
    # Foreign currency detected.
    assert any("devise" in i.lower() for i in issues)
    assert "usd" in text
    # Anglo-saxon number format detected.
    assert any("anglo-saxon" in i.lower() for i in issues)
    # CTA in another language detected.
    assert any("cta" in i.lower() for i in issues)


def test_audit_page_clean_fr_page_has_no_issues():
    issues = audit_page(
        locale="fr",
        body_text=(
            "Découvrez notre offre à 49,00 € par mois. "
            "Plus de 1 000 clients nous font confiance. "
            "Consultez nos mentions légales et notre politique de confidentialité."
        ),
        cta_texts=["Acheter maintenant", "En savoir plus", "Découvrir l'offre"],
    )
    assert issues == []


def test_audit_page_unknown_locale_returns_empty():
    assert audit_page(locale="", body_text="anything", cta_texts=["Buy now"]) == []
    assert audit_page(locale="ja", body_text="anything", cta_texts=[]) == []
