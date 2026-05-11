"""Generate ready-to-paste JSON-LD for pages that are missing useful schema.

Given a page's type (from page_classifier) and the schema @types already
present, propose the most relevant missing JSON-LD block, filled with the
crawl data we have (title, URL, description, images, organization name…)
and `[À COMPLÉTER : …]` placeholders for fields we can't observe.

Pure Python — no LLM call.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

# Which @type each page type should ideally carry.
_TYPE_TO_SCHEMA = {
    "homepage": "Organization",
    "article": "Article",
    "product": "Product",
    "service": "Service",
    "localBusiness": "LocalBusiness",
    "faq": "FAQPage",
    "contact": "ContactPage",
    "about": "AboutPage",
    "category": "CollectionPage",
}

# If any of these are already present, we don't suggest the corresponding one.
_ALREADY_COVERED = {
    "Organization": {"organization", "localbusiness"},
    "Article": {"article", "blogposting", "newsarticle"},
    "Product": {"product"},
    "Service": {"service"},
    "LocalBusiness": {"localbusiness", "restaurant", "store", "professionalservice"},
    "FAQPage": {"faqpage"},
    "ContactPage": {"contactpage"},
    "AboutPage": {"aboutpage"},
    "CollectionPage": {"collectionpage", "itemlist"},
}

_PH_ORG = "[À COMPLÉTER : nom de l'organisation]"
_PH_PHONE = "[À COMPLÉTER : +33 X XX XX XX XX]"
_PH_ADDR = "[À COMPLÉTER : rue]"
_PH_CITY = "[À COMPLÉTER : ville]"
_PH_ZIP = "[À COMPLÉTER : code postal]"
_PH_AUTHOR = "[À COMPLÉTER : nom de l'auteur]"
_PH_DATE = "[À COMPLÉTER : 2026-01-01]"
_PH_PRICE = "[À COMPLÉTER : 0.00]"


def _site_name(domain: str) -> str:
    # "exemple.com" -> "Exemple"
    host = domain.split(":")[0]
    base = host.split(".")[-2] if host.count(".") >= 1 else host
    return base.replace("-", " ").title()


def _pick_image(images: list[str]) -> str:
    return images[0] if images else "[À COMPLÉTER : URL d'une image représentative]"


def suggest_schema(
    *,
    url: str,
    page_type: str,
    existing_types: list[str],
    title: str = "",
    h1: str = "",
    meta_description: str | None = None,
    image_urls: list[str] | None = None,
    domain: str = "",
    headings_questions: list[str] | None = None,
) -> tuple[str, str]:
    """Return (json_ld_string, schema_type_name) or ("", "") if nothing useful
    to add."""
    image_urls = image_urls or []
    existing_lower = {t.lower() for t in (existing_types or [])}
    target = _TYPE_TO_SCHEMA.get(page_type)
    if not target:
        return "", ""
    if existing_lower & _ALREADY_COVERED.get(target, set()):
        return "", ""

    name = title or h1 or url
    desc = meta_description or f"{h1 or title}"
    org = _site_name(domain) if domain else _PH_ORG
    site_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    if target == "Organization":
        obj = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": org if org and "[À COMPLÉTER" not in org else _PH_ORG,
            "url": site_url,
            "logo": _pick_image(image_urls),
            "sameAs": ["[À COMPLÉTER : URL réseaux sociaux, une par ligne]"],
            "contactPoint": {
                "@type": "ContactPoint",
                "telephone": _PH_PHONE,
                "contactType": "customer service",
            },
        }
    elif target == "Article":
        obj = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": (h1 or title)[:110] or _PH_AUTHOR,
            "description": desc,
            "image": [_pick_image(image_urls)],
            "author": {"@type": "Person", "name": _PH_AUTHOR},
            "publisher": {
                "@type": "Organization",
                "name": org if "[À COMPLÉTER" not in org else _PH_ORG,
                "logo": {"@type": "ImageObject", "url": _pick_image(image_urls)},
            },
            "datePublished": _PH_DATE,
            "dateModified": _PH_DATE,
            "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        }
    elif target == "Product":
        obj = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": name,
            "description": desc,
            "image": [_pick_image(image_urls)],
            "brand": {"@type": "Brand", "name": org if "[À COMPLÉTER" not in org else _PH_ORG},
            "offers": {
                "@type": "Offer",
                "url": url,
                "priceCurrency": "EUR",
                "price": _PH_PRICE,
                "availability": "https://schema.org/InStock",
            },
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "[À COMPLÉTER : 4.5]",
                "reviewCount": "[À COMPLÉTER : 12]",
            },
        }
    elif target == "Service":
        obj = {
            "@context": "https://schema.org",
            "@type": "Service",
            "name": name,
            "description": desc,
            "provider": {
                "@type": "Organization",
                "name": org if "[À COMPLÉTER" not in org else _PH_ORG,
                "url": site_url,
            },
            "areaServed": "[À COMPLÉTER : ville / région desservie]",
            "url": url,
        }
    elif target == "LocalBusiness":
        obj = {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": org if "[À COMPLÉTER" not in org else _PH_ORG,
            "image": _pick_image(image_urls),
            "url": site_url,
            "telephone": _PH_PHONE,
            "address": {
                "@type": "PostalAddress",
                "streetAddress": _PH_ADDR,
                "addressLocality": _PH_CITY,
                "postalCode": _PH_ZIP,
                "addressCountry": "FR",
            },
            "openingHoursSpecification": [
                {
                    "@type": "OpeningHoursSpecification",
                    "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                    "opens": "[À COMPLÉTER : 09:00]",
                    "closes": "[À COMPLÉTER : 18:00]",
                }
            ],
            "priceRange": "[À COMPLÉTER : €€]",
        }
    elif target == "FAQPage":
        questions = headings_questions or []
        main = [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": "[À COMPLÉTER : réponse]"},
            }
            for q in questions[:8]
        ] or [
            {
                "@type": "Question",
                "name": "[À COMPLÉTER : question]",
                "acceptedAnswer": {"@type": "Answer", "text": "[À COMPLÉTER : réponse]"},
            }
        ]
        obj = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": main,
        }
    elif target == "ContactPage":
        obj = {
            "@context": "https://schema.org",
            "@type": "ContactPage",
            "name": name,
            "url": url,
            "mainEntity": {
                "@type": "Organization",
                "name": org if "[À COMPLÉTER" not in org else _PH_ORG,
                "telephone": _PH_PHONE,
                "email": "[À COMPLÉTER : contact@exemple.com]",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": _PH_ADDR,
                    "addressLocality": _PH_CITY,
                    "postalCode": _PH_ZIP,
                    "addressCountry": "FR",
                },
            },
        }
    elif target == "AboutPage":
        obj = {
            "@context": "https://schema.org",
            "@type": "AboutPage",
            "name": name,
            "url": url,
            "about": {
                "@type": "Organization",
                "name": org if "[À COMPLÉTER" not in org else _PH_ORG,
                "url": site_url,
            },
        }
    elif target == "CollectionPage":
        obj = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": name,
            "url": url,
            "description": desc,
        }
    else:
        return "", ""

    return json.dumps(obj, ensure_ascii=False, indent=2), target
