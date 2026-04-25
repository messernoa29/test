"""llms.txt generator.

Builds an llms.txt file (https://llmstxt.org) for a target site:
- Title (site name from <title> or domain)
- Short summary (meta description of the homepage)
- Sections grouping discovered URLs by URL prefix, each with title + description.

Reuses the project's deterministic HTTP crawler so the output mirrors what an
audit would surface.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

from api.services.crawler import crawl

logger = logging.getLogger(__name__)


SECTION_LABELS: dict[str, str] = {
    "blog": "Blog",
    "articles": "Articles",
    "news": "Actualités",
    "actualites": "Actualités",
    "actu": "Actualités",
    "produits": "Produits",
    "products": "Produits",
    "shop": "Boutique",
    "boutique": "Boutique",
    "services": "Services",
    "solutions": "Solutions",
    "docs": "Documentation",
    "documentation": "Documentation",
    "guides": "Guides",
    "guide": "Guides",
    "tutoriels": "Tutoriels",
    "tutorials": "Tutoriels",
    "ressources": "Ressources",
    "resources": "Ressources",
    "support": "Support",
    "aide": "Aide",
    "help": "Aide",
    "faq": "FAQ",
    "contact": "Contact",
    "about": "À propos",
    "a-propos": "À propos",
    "qui-sommes-nous": "À propos",
    "team": "Équipe",
    "equipe": "Équipe",
    "carriere": "Carrières",
    "careers": "Carrières",
    "jobs": "Carrières",
    "case-studies": "Études de cas",
    "case-study": "Études de cas",
    "etudes-de-cas": "Études de cas",
    "portfolio": "Portfolio",
    "realisations": "Réalisations",
    "events": "Événements",
    "evenements": "Événements",
    "legal": "Mentions légales",
    "mentions-legales": "Mentions légales",
    "privacy": "Confidentialité",
    "confidentialite": "Confidentialité",
}


def generate_llms_txt(url: str) -> str:
    """Crawl `url` then return the rendered llms.txt content."""
    crawl_data = crawl(url)
    pages = crawl_data.pages
    if not pages:
        raise ValueError("Aucune page exploitable trouvée sur ce site.")

    domain = crawl_data.domain
    home = _pick_home(pages, crawl_data.url) or pages[0]

    title = _site_title(home, domain)
    summary = (home.metaDescription or "").strip()

    grouped: dict[str, list] = defaultdict(list)
    home_url = home.url.rstrip("/")
    for page in pages:
        if page.url.rstrip("/") == home_url:
            continue
        section = _section_for(page.url)
        grouped[section].append(page)

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    if summary:
        lines.append(f"> {summary}")
        lines.append("")
    lines.append(f"- [Accueil]({home.url}): {_describe(home)}")
    lines.append("")

    for section_key in _ordered_sections(grouped.keys()):
        label = _section_label(section_key)
        lines.append(f"## {label}")
        lines.append("")
        for page in grouped[section_key][:30]:
            link_title = _link_title(page)
            desc = _describe(page)
            if desc:
                lines.append(f"- [{link_title}]({page.url}): {desc}")
            else:
                lines.append(f"- [{link_title}]({page.url})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _pick_home(pages, base_url: str):
    base = base_url.rstrip("/")
    for p in pages:
        if p.url.rstrip("/") == base:
            return p
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    for p in pages:
        if p.url.rstrip("/") == root:
            return p
    return None


def _site_title(home, domain: str) -> str:
    if home.title:
        # Strip trailing branding "| Foo" if title is long
        raw = home.title.strip()
        for sep in (" | ", " — ", " - ", " · "):
            if sep in raw and len(raw) > 60:
                raw = raw.split(sep, 1)[0].strip()
                break
        return raw or domain
    return domain


def _section_for(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "_root"
    first = path.split("/", 1)[0].lower()
    return first or "_root"


def _section_label(key: str) -> str:
    if key == "_root":
        return "Pages principales"
    if key in SECTION_LABELS:
        return SECTION_LABELS[key]
    cleaned = key.replace("-", " ").replace("_", " ").strip()
    return cleaned.capitalize() if cleaned else "Pages"


def _ordered_sections(keys) -> list[str]:
    keys = list(keys)
    priority = [
        "_root",
        "services",
        "solutions",
        "produits",
        "products",
        "shop",
        "boutique",
        "blog",
        "articles",
        "news",
        "actualites",
        "case-studies",
        "case-study",
        "etudes-de-cas",
        "portfolio",
        "realisations",
        "docs",
        "documentation",
        "guides",
        "ressources",
        "resources",
        "about",
        "a-propos",
        "team",
        "equipe",
        "contact",
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for k in priority:
        if k in keys:
            ordered.append(k)
            seen.add(k)
    for k in sorted(keys):
        if k not in seen:
            ordered.append(k)
    return ordered


def _link_title(page) -> str:
    return (page.h1 or page.title or _slug_to_title(page.url)).strip()


def _describe(page) -> str:
    desc = (page.metaDescription or "").strip()
    if desc:
        return _trim(desc, 180)
    snip = (page.textSnippet or "").strip()
    if snip:
        return _trim(snip, 180)
    return ""


def _slug_to_title(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "Accueil"
    last = path.rsplit("/", 1)[-1]
    return last.replace("-", " ").replace("_", " ").strip().capitalize() or last


def _trim(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:.") + "…"
