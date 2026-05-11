"""Tests for api.services.page_classifier.classify_page (pure heuristics)."""

from __future__ import annotations

from api.services.page_classifier import classify_page


def test_homepage_by_flag():
    assert classify_page(url="https://exemple.com/quelque-chose", is_homepage=True) == "homepage"


def test_homepage_by_root_path():
    assert classify_page(url="https://exemple.com/") == "homepage"
    assert classify_page(url="https://exemple.com") == "homepage"


def test_article_by_path_and_wordcount():
    t = classify_page(
        url="https://exemple.com/blog/mon-super-guide",
        h1="Mon super guide",
        word_count=1800,
    )
    assert t == "article"


def test_article_fallback_long_content():
    # No path hint, but long-form with an H1 -> article fallback.
    t = classify_page(
        url="https://exemple.com/ressources/lecture",
        h1="Une longue lecture",
        word_count=900,
    )
    assert t == "article"


def test_product_by_price_snippet():
    t = classify_page(
        url="https://exemple.com/catalogue/chaise-design-x42",
        title="Chaise design",
        text_snippet="Ajouter au panier — prix 149 € livraison incluse",
        word_count=300,
    )
    assert t == "product"


def test_faq_by_headings_and_text():
    # URL doesn't hint anything -> the content heuristic ("foire aux questions"
    # + a "?" heading) must kick in.
    t = classify_page(
        url="https://exemple.com/centre-ressources",
        title="Vos questions",
        headings=["Comment fonctionne le service ?", "Quels moyens de paiement ?"],
        text_snippet="Foire aux questions sur notre offre",
        word_count=500,
    )
    assert t == "faq"


def test_contact_by_snippet_and_low_wordcount():
    t = classify_page(
        url="https://exemple.com/joindre-equipe",
        title="Joignez-nous",
        text_snippet="Formulaire de contact — adresse, téléphone, horaires d'ouverture",
        word_count=120,
    )
    assert t == "contact"


def test_existing_schema_wins_over_heuristics():
    # URL/path screams "blog/article", but the page declares a Product schema.
    t = classify_page(
        url="https://exemple.com/blog/mon-article",
        h1="Mon article",
        word_count=2000,
        schemas=["Product"],
    )
    assert t == "product"


def test_faqpage_schema_wins():
    t = classify_page(
        url="https://exemple.com/anything",
        schemas=["FAQPage"],
        word_count=2000,
        h1="Whatever",
    )
    assert t == "faq"


def test_localbusiness_schema_match():
    assert classify_page(url="https://exemple.com/page", schemas=["LocalBusiness"]) == "localBusiness"
    # "restaurant" is special-cased too.
    assert classify_page(url="https://exemple.com/resto", schemas=["Restaurant"]) == "localBusiness"


def test_fallback_other():
    t = classify_page(
        url="https://exemple.com/page-quelconque",
        title="Page",
        h1="",
        text_snippet="rien de particulier ici",
        word_count=150,
    )
    assert t == "other"
