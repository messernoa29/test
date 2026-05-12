"""Prospect Sheet — produce a pre-meeting brief from a company's website.

Pipeline :
1. Fetch the home page (and a couple of key pages — about / contact / mentions
   légales) over plain HTTP.
2. Fingerprint the tech stack from the raw HTML + response headers
   (`tech_detector.detect_tech_stack`).
3. Ask the LLM (with web-search grounding) to fill in the company identity and
   a decision-maker persona + tailored prospecting angles, given the URL, the
   page titles/metas, a text excerpt, and the already-detected stack. Strict
   anti-hallucination instructions: empty / null when unknown.

If the LLM step fails we still return the detected stack + a minimal identity
(name from the page title) so the sheet is never useless.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from api.models import (
    DetectedTech,
    ProspectCompanyIdentity,
    ProspectPersona,
    ProspectSheet,
    ProspectStackByCategory,
)
from api.services.llm import LLMResponse, get_llm_client
from api.services.tech_detector import detect_tech_stack

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; AuditBureauBot/0.1; +https://audit-bureau.local)"
)
_REQUEST_TIMEOUT = 15.0
# Relative paths probed in addition to the home page (first hits win).
_KEY_PATHS = [
    "/a-propos", "/a-propos/", "/about", "/about/", "/about-us",
    "/qui-sommes-nous", "/notre-histoire",
    "/contact", "/contact/", "/nous-contacter",
    "/mentions-legales", "/mentions-legales/", "/legal", "/legal-notice",
]
_MAX_EXTRA_PAGES = 3
_MAX_TEXT_EXCERPT = 6000


_SYSTEM = (
    "Tu es un analyste commercial qui prépare des fiches prospect avant des "
    "rendez-vous de prospection. Tu travailles à partir de ce qui est "
    "réellement observable sur le site web de l'entreprise (+ une recherche "
    "web légère si nécessaire). RÈGLE ABSOLUE : tu n'inventes rien. Si une "
    "information est inconnue, tu laisses la chaîne vide \"\" ou null — jamais "
    "de supposition présentée comme un fait. "
    "SORTIE : uniquement le bloc <PROSPECT_JSON>{...}</PROSPECT_JSON>, sans "
    "aucun texte autour, toujours fermé par </PROSPECT_JSON>. Français concis."
)

_TEMPLATE = """Prépare une fiche prospect à partir du site web ci-dessous.

URL : {url}
Domaine : {domain}

Titres de page repérés :
{titles}

Méta-descriptions repérées :
{metas}

Extrait du texte des pages (tronqué) :
{excerpt}

Stack technique DÉJÀ détecté automatiquement (ne le recopie pas, sers-t'en pour le persona) :
{stack_summary}

Produis :
- identity :
  - name : raison sociale ou nom commercial deviné depuis le site/titre (vide si vraiment indéterminable)
  - location : ville et pays (depuis adresse, mentions légales, schema LocalBusiness, ou recherche web ; vide si inconnu)
  - sector : secteur d'activité en quelques mots
  - estimatedFoundedYear : année de création estimée (entier) ou null si inconnu
  - estimatedSize : "TPE" | "PME" | "ETI" | "Grande entreprise" — estimation prudente, vide si impossible à estimer
  - socialProfiles : URLs des profils réseaux sociaux trouvés sur le site (LinkedIn, Instagram, Facebook, X, YouTube…), liste vide sinon
  - onlinePresenceNotes : 1-2 phrases sur la présence en ligne (avis Google si mentionnés, blog actif, etc.)
  - valueProposition : 1-2 phrases sur le positionnement / la proposition de valeur affichée
- persona :
  - likelyContactRoles : 1-3 rôles probables à contacter (ex : "Dirigeant·e", "Responsable marketing", "Responsable e-commerce", "DSI") selon la taille et le secteur
  - likelyPriorities : 2-4 priorités / douleurs probables de ce décideur
  - approachAngles : 2-4 accroches de prospection PERSONNALISÉES, ancrées sur ce qui a réellement été observé sur le site (ex : "site WordPress sans plugin SEO détecté → ouverture sur l'optimisation on-page" ; "aucun Meta Pixel détecté → ils ne font peut-être pas de retargeting")

Sortie STRICTE :

<PROSPECT_JSON>
{{
  "identity": {{
    "name": "...",
    "location": "...",
    "sector": "...",
    "estimatedFoundedYear": null,
    "estimatedSize": "...",
    "socialProfiles": ["..."],
    "onlinePresenceNotes": "...",
    "valueProposition": "..."
  }},
  "persona": {{
    "likelyContactRoles": ["..."],
    "likelyPriorities": ["..."],
    "approachAngles": ["..."]
  }}
}}
</PROSPECT_JSON>
"""


def create_sheet(url: str) -> ProspectSheet:
    """Create a pending sheet for `url`."""
    clean = url.strip()
    domain = (urlparse(clean).netloc or clean).lower()
    return ProspectSheet(
        id=uuid.uuid4().hex,
        url=clean,
        domain=domain,
        createdAt=datetime.now(timezone.utc).isoformat(),
        status="pending",
    )


def run_pipeline(sheet: ProspectSheet) -> ProspectSheet:
    """Run fetch → fingerprint → LLM enrichment. Always ends done/failed."""
    try:
        pages = _fetch_pages(sheet.url)
        if not pages:
            raise RuntimeError(
                "Impossible de récupérer la page d'accueil du site (timeout, "
                "blocage, ou site indisponible)."
            )
        home_html, home_headers = pages[0][1], pages[0][2]
        stack = detect_tech_stack(home_html, home_headers)

        identity, persona = _enrich_with_llm(sheet.url, sheet.domain, pages, stack)
        return sheet.model_copy(
            update={
                "status": "done",
                "identity": identity,
                "stack": stack,
                "persona": persona,
                "error": None,
            }
        )
    except Exception as e:
        logger.exception("Prospect pipeline failed for %s: %s", sheet.id, e)
        return sheet.model_copy(
            update={"status": "failed", "error": str(e) or e.__class__.__name__}
        )


# ---------------------------------------------------------------------------
# Internals


def _fetch_pages(url: str) -> list[tuple[str, str, dict]]:
    """Return [(url, html, headers)] — home first, then up to N key pages."""
    out: list[tuple[str, str, dict]] = []
    headers = {"User-Agent": _USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7"}
    try:
        client = httpx.Client(
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            verify=False,  # prospect sites often have sloppy TLS; we only read HTML
        )
    except Exception as e:
        logger.warning("httpx client init failed: %s", e)
        return out
    try:
        home = _get(client, url)
        if home is None:
            return out
        out.append(home)
        origin = "{0.scheme}://{0.netloc}".format(urlparse(home[0]))
        seen_paths = {urlparse(home[0]).path or "/"}
        for path in _KEY_PATHS:
            if len(out) > _MAX_EXTRA_PAGES:
                break
            if path in seen_paths:
                continue
            page = _get(client, urljoin(origin + "/", path.lstrip("/")))
            if page is None:
                continue
            seen_paths.add(path)
            out.append(page)
    finally:
        client.close()
    return out


def _get(client: httpx.Client, url: str) -> Optional[tuple[str, str, dict]]:
    try:
        resp = client.get(url)
    except httpx.HTTPError as e:
        logger.debug("Fetch failed for %s: %s", url, e)
        return None
    if resp.status_code >= 400:
        return None
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype.lower() and ctype:
        return None
    try:
        text = resp.text
    except Exception:
        return None
    if not text or not text.strip():
        return None
    return (str(resp.url), text, dict(resp.headers))


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]*content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _extract_title(html: str) -> str:
    m = _TITLE_RE.search(html)
    if not m:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub("", m.group(1))).strip()[:200]


def _extract_meta_desc(html: str) -> str:
    m = _META_DESC_RE.search(html)
    if not m:
        # also try content-before-name ordering
        alt = re.search(
            r'<meta[^>]+content=["\'](.*?)["\'][^>]*name=["\']description["\']',
            html, re.IGNORECASE | re.DOTALL,
        )
        if not alt:
            return ""
        return _WS_RE.sub(" ", alt.group(1)).strip()[:300]
    return _WS_RE.sub(" ", m.group(1)).strip()[:300]


def _visible_text(html: str) -> str:
    # crude: drop script/style, strip tags, collapse whitespace
    cleaned = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"&[a-z]+;|&#\d+;", " ", cleaned, flags=re.IGNORECASE)
    return _WS_RE.sub(" ", cleaned).strip()


def _stack_summary(stack: ProspectStackByCategory) -> str:
    parts: list[str] = []
    cat_labels = {
        "cms": "CMS",
        "analytics": "Analytics",
        "advertising": "Tags publicitaires",
        "chatCrm": "Chat / CRM",
        "hostingCdn": "Hébergeur / CDN",
        "other": "Autre",
    }
    for attr, label in cat_labels.items():
        items: list[DetectedTech] = getattr(stack, attr)
        if items:
            names = ", ".join(f"{t.name} ({t.confidence})" for t in items)
            parts.append(f"- {label} : {names}")
        else:
            parts.append(f"- {label} : rien détecté")
    return "\n".join(parts)


def _enrich_with_llm(
    url: str,
    domain: str,
    pages: list[tuple[str, str, dict]],
    stack: ProspectStackByCategory,
) -> tuple[ProspectCompanyIdentity, ProspectPersona]:
    titles: list[str] = []
    metas: list[str] = []
    text_parts: list[str] = []
    for page_url, html, _ in pages:
        t = _extract_title(html)
        if t:
            titles.append(f"{page_url} → {t}")
        d = _extract_meta_desc(html)
        if d:
            metas.append(f"{page_url} → {d}")
        text_parts.append(_visible_text(html))

    excerpt = " \n".join(text_parts)[:_MAX_TEXT_EXCERPT]
    fallback_name = ""
    if titles:
        # take the first title's left-most chunk before a separator
        raw = titles[0].split("→", 1)[-1].strip()
        fallback_name = re.split(r"\s+[|\-–—·»]\s+", raw)[0].strip()[:120]

    prompt = _TEMPLATE.format(
        url=url,
        domain=domain,
        titles="\n".join(titles) or "(aucun)",
        metas="\n".join(metas) or "(aucune)",
        excerpt=excerpt or "(texte indisponible)",
        stack_summary=_stack_summary(stack),
    )

    try:
        response = get_llm_client().generate(
            system=_SYSTEM,
            user_prompt=prompt,
            max_tokens=4000,
            enable_web_search=True,
            temperature=0.0,
        )
    except Exception as e:
        logger.warning("Prospect LLM enrichment failed: %s", e)
        return (
            ProspectCompanyIdentity(
                name=fallback_name or domain,
                onlinePresenceNotes="Analyse IA partielle — enrichissement automatique indisponible.",
            ),
            ProspectPersona(),
        )

    payload = _extract_json(response, tag="PROSPECT_JSON")
    if payload is None:
        return (
            ProspectCompanyIdentity(
                name=fallback_name or domain,
                onlinePresenceNotes="Analyse IA partielle — la synthèse n'a pas produit de JSON exploitable.",
            ),
            ProspectPersona(),
        )

    identity = _parse_identity(payload.get("identity"), fallback_name or domain)
    persona = _parse_persona(payload.get("persona"))
    return identity, persona


def _parse_identity(raw: object, fallback_name: str) -> ProspectCompanyIdentity:
    if not isinstance(raw, dict):
        return ProspectCompanyIdentity(name=fallback_name)
    try:
        identity = ProspectCompanyIdentity.model_validate(raw)
    except Exception as e:
        logger.debug("Bad identity payload: %s", e)
        return ProspectCompanyIdentity(name=fallback_name)
    if not (identity.name or "").strip():
        identity = identity.model_copy(update={"name": fallback_name})
    return identity


def _parse_persona(raw: object) -> ProspectPersona:
    if not isinstance(raw, dict):
        return ProspectPersona()
    try:
        return ProspectPersona.model_validate(raw)
    except Exception as e:
        logger.debug("Bad persona payload: %s", e)
        return ProspectPersona()


_OPEN_TAG_RE_CACHE: dict[str, re.Pattern] = {}


def _open_tag_re(tag: str) -> re.Pattern:
    if tag not in _OPEN_TAG_RE_CACHE:
        _OPEN_TAG_RE_CACHE[tag] = re.compile(f"<{tag}>", re.IGNORECASE)
    return _OPEN_TAG_RE_CACHE[tag]


def _extract_json(response: LLMResponse, *, tag: str) -> Optional[dict]:
    text = response.text
    if not text:
        return None
    m = _open_tag_re(tag).search(text)
    start = text.find("{", m.end()) if m else text.find("{")
    if start < 0:
        logger.warning("%s extraction: no opening brace (stop=%s)", tag, response.stop_reason)
        return None
    candidate = _scan_balanced(text, start)
    if candidate is None:
        logger.warning("%s extraction: truncated", tag)
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        logger.warning("%s JSON invalid: %s", tag, e)
        return None
    return parsed if isinstance(parsed, dict) else None


def _scan_balanced(text: str, start: int) -> Optional[str]:
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
