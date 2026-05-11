"""Heuristic page-type classification from crawl signals.

Used by the schema generator (which schema fits) and the SXO check (does
the page type match what Google ranks for this query). Deliberately simple
and deterministic — no LLM call. Returns one of:

  homepage | article | product | service | localBusiness | faq | contact |
  category | about | other
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# URL path keyword → type. First match wins, order matters.
_PATH_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"/(blog|article|actualit|news|post|guide|tuto)", re.I), "article"),
    (re.compile(r"/(product|produit|shop|boutique|p/|item)", re.I), "product"),
    (re.compile(r"/(service|prestation|offre)", re.I), "service"),
    (re.compile(r"/(faq|questions?-frequentes|aide|help|support)", re.I), "faq"),
    (re.compile(r"/(contact|nous-contacter)", re.I), "contact"),
    (re.compile(r"/(about|a-propos|qui-sommes-nous|notre-equipe|team)", re.I), "about"),
    (re.compile(r"/(categor|collection|rubrique)", re.I), "category"),
]

_FAQ_TEXT_HINT = re.compile(r"(foire aux questions|questions fr[ée]quentes|f\.?a\.?q\.?)", re.I)
_PRICE_HINT = re.compile(r"(€|\bEUR\b|\bUSD\b|\$|prix|tarif|à partir de|add to cart|ajouter au panier|acheter)", re.I)
_CONTACT_HINT = re.compile(r"(formulaire de contact|nous écrire|envoyez-nous|adresse|téléphone|horaires d'ouverture)", re.I)
_LOCAL_HINT = re.compile(r"(horaires d'ouverture|nous trouver|plan d'accès|itinéraire|opening hours|find us|directions)", re.I)


def classify_page(
    *,
    url: str,
    title: str = "",
    h1: str = "",
    headings: list[str] | None = None,
    text_snippet: str = "",
    schemas: list[str] | None = None,
    word_count: int = 0,
    is_homepage: bool = False,
) -> str:
    """Return the most likely page type. `schemas` is the list of @type strings
    already found on the page (used as a strong signal)."""
    headings = headings or []
    schemas = [s.lower() for s in (schemas or [])]
    path = urlparse(url).path or "/"

    # 1. Existing schema is the strongest signal.
    if any(s in ("product",) for s in schemas):
        return "product"
    if any(s in ("faqpage",) for s in schemas):
        return "faq"
    if any(s in ("article", "blogposting", "newsarticle") for s in schemas):
        return "article"
    if any(s in ("localbusiness",) or s.endswith("business") for s in schemas) or "restaurant" in schemas:
        return "localBusiness"
    if any(s in ("contactpage",) for s in schemas):
        return "contact"
    if any(s in ("aboutpage",) for s in schemas):
        return "about"
    if any(s in ("collectionpage", "itemlist") for s in schemas):
        return "category"

    # 2. Homepage.
    if is_homepage or path in ("", "/"):
        return "homepage"

    # 3. URL path hints.
    for pat, t in _PATH_HINTS:
        if pat.search(path):
            return t

    # 4. Content hints.
    blob = " ".join([title, h1, " ".join(headings), text_snippet])
    if _FAQ_TEXT_HINT.search(blob) and any("?" in h for h in headings):
        return "faq"
    if _CONTACT_HINT.search(blob) and word_count < 400:
        return "contact"
    if _LOCAL_HINT.search(blob):
        return "localBusiness"
    if _PRICE_HINT.search(blob):
        return "product"

    # 5. Article fallback: long-form content with a clear H1.
    if word_count >= 600 and h1:
        return "article"

    return "other"
