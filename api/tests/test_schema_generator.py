"""Tests for api.services.schema_generator.suggest_schema (pure JSON-LD builder)."""

from __future__ import annotations

import json

from api.services.schema_generator import suggest_schema


def _parse(json_ld: str) -> dict:
    obj = json.loads(json_ld)
    assert obj["@context"] == "https://schema.org"
    return obj


def test_article_for_article_page():
    json_ld, schema_type = suggest_schema(
        url="https://exemple.com/blog/mon-article",
        page_type="article",
        existing_types=[],
        title="Mon article",
        h1="Mon article",
        meta_description="Une description",
        image_urls=["https://exemple.com/img/cover.jpg"],
        domain="exemple.com",
    )
    assert schema_type == "Article"
    obj = _parse(json_ld)
    assert obj["@type"] == "Article"
    assert obj["headline"] == "Mon article"
    assert obj["image"] == ["https://exemple.com/img/cover.jpg"]
    # Non-observable fields get placeholders.
    assert "[À COMPLÉTER" in json.dumps(obj, ensure_ascii=False)
    assert obj["author"]["name"].startswith("[À COMPLÉTER")
    assert obj["datePublished"].startswith("[À COMPLÉTER")


def test_localbusiness_for_localbusiness_page():
    json_ld, schema_type = suggest_schema(
        url="https://exemple.com/contact",
        page_type="localBusiness",
        existing_types=[],
        domain="ma-boite.fr",
    )
    assert schema_type == "LocalBusiness"
    obj = _parse(json_ld)
    assert obj["@type"] == "LocalBusiness"
    assert obj["address"]["addressCountry"] == "FR"
    assert "[À COMPLÉTER" in obj["address"]["streetAddress"]


def test_product_for_product_page():
    json_ld, schema_type = suggest_schema(
        url="https://exemple.com/p/chaise",
        page_type="product",
        existing_types=[],
        title="Chaise",
        domain="exemple.com",
    )
    assert schema_type == "Product"
    obj = _parse(json_ld)
    assert obj["@type"] == "Product"
    assert obj["offers"]["priceCurrency"] == "EUR"
    assert obj["offers"]["price"].startswith("[À COMPLÉTER")


def test_organization_for_homepage():
    json_ld, schema_type = suggest_schema(
        url="https://exemple.com/",
        page_type="homepage",
        existing_types=[],
        domain="exemple.com",
    )
    assert schema_type == "Organization"
    obj = _parse(json_ld)
    assert obj["@type"] == "Organization"
    assert obj["url"] == "https://exemple.com"
    assert obj["name"] == "Exemple"  # derived from domain


def test_faqpage_uses_passed_questions():
    questions = ["Comment ça marche ?", "Combien ça coûte ?"]
    json_ld, schema_type = suggest_schema(
        url="https://exemple.com/faq",
        page_type="faq",
        existing_types=[],
        headings_questions=questions,
    )
    assert schema_type == "FAQPage"
    obj = _parse(json_ld)
    assert obj["@type"] == "FAQPage"
    names = [q["name"] for q in obj["mainEntity"]]
    assert names == questions
    for q in obj["mainEntity"]:
        assert q["acceptedAnswer"]["text"].startswith("[À COMPLÉTER")


def test_faqpage_without_questions_has_placeholder():
    json_ld, schema_type = suggest_schema(
        url="https://exemple.com/faq",
        page_type="faq",
        existing_types=[],
    )
    obj = _parse(json_ld)
    assert len(obj["mainEntity"]) == 1
    assert obj["mainEntity"][0]["name"].startswith("[À COMPLÉTER")


def test_returns_empty_when_type_already_covered():
    # Article page that already has BlogPosting -> nothing to add.
    json_ld, schema_type = suggest_schema(
        url="https://exemple.com/blog/x",
        page_type="article",
        existing_types=["BlogPosting"],
    )
    assert (json_ld, schema_type) == ("", "")

    # Homepage that already has Organization.
    assert suggest_schema(
        url="https://exemple.com/",
        page_type="homepage",
        existing_types=["Organization"],
    ) == ("", "")

    # localBusiness page that already declares LocalBusiness.
    assert suggest_schema(
        url="https://exemple.com/contact",
        page_type="localBusiness",
        existing_types=["LocalBusiness"],
    ) == ("", "")


def test_returns_empty_for_unknown_page_type():
    assert suggest_schema(url="https://exemple.com/x", page_type="other", existing_types=[]) == ("", "")
