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
    "/contact", "/contact/", "/nous-contacter", "/contactez-nous",
    "/equipe", "/equipe/", "/notre-equipe", "/team", "/our-team", "/about/team",
    "/a-propos", "/a-propos/", "/about", "/about/", "/about-us",
    "/qui-sommes-nous", "/notre-histoire",
    "/mentions-legales", "/mentions-legales/", "/legal", "/legal-notice", "/imprint",
]
_MAX_EXTRA_PAGES = 5
_MAX_TEXT_EXCERPT = 7000


_SYSTEM = (
    "Tu es un analyste commercial qui prépare des fiches prospect avant des "
    "rendez-vous de prospection B2B. Tu travailles à partir de ce qui est "
    "réellement observable sur le site web de l'entreprise ET d'une recherche "
    "web ciblée. RÈGLE ABSOLUE : tu n'inventes rien et tu ne devines aucune "
    "coordonnée. Si une information est inconnue, tu laisses la chaîne vide "
    "\"\" ou null — jamais de supposition présentée comme un fait.\n"
    "RÈGLE COORDONNÉES : un email ou un téléphone ne peut être attribué à une "
    "PERSONNE que si une source montre explicitement « cette coordonnée "
    "appartient à cette personne » (page équipe avec email à côté du nom, "
    "signature, carte de visite publiée…). Dans ce cas, sourceUrl est "
    "OBLIGATOIRE. Ne JAMAIS rattacher à une personne un numéro/email qui "
    "figure ailleurs sur le site sans lien explicite — mets-le plutôt dans "
    "companyEmails/companyPhones. Ne JAMAIS deviner un email type "
    "prenom.nom@domaine. En cas de doute : champ vide.\n"
    "SOURCES À UTILISER (recherche web) : annuaires légaux (Pappers, "
    "Societe.com, Infogreffe — fiables pour raison sociale, dirigeants "
    "officiels, date de création, adresse du siège) ; le site de l'entreprise "
    "(pages équipe / contact / mentions légales — priorité pour rattacher une "
    "coordonnée à une personne) ; articles de presse / interviews / "
    "communiqués (pour confirmer des rôles explicites « X, directeur "
    "marketing de … ») ; résultats LinkedIn PUBLICS tels qu'ils apparaissent "
    "dans la recherche (pour confirmer nom+rôle UNIQUEMENT — jamais de "
    "numéro/email privé, et tu n'ouvres pas les pages linkedin.com).\n"
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

Coordonnées brutes extraites automatiquement du site (à attribuer aux personnes / à l'entreprise) :
{contacts_raw}

Utilise web_search de façon CIBLÉE :
- "{domain} Pappers" / "{domain} Societe.com" / "<raison sociale> Infogreffe" → dirigeants officiels, date de création, adresse du siège, raison sociale
- "<raison sociale> directeur marketing" / "... responsable digital" / "... CEO" → confirmer des rôles explicites dans des articles/communiqués/pages d'équipe
- recherche du nom de l'entreprise sur les pages équipe / "qui sommes-nous" si non déjà crawlées
- les extraits LinkedIn publics renvoyés par la recherche peuvent confirmer un nom+rôle (jamais ouvrir linkedin.com, jamais de numéro/email privé)

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
  - approachAngles : 2-4 accroches de prospection PERSONNALISÉES, ancrées sur ce qui a réellement été observé sur le site
  - contacts : liste des PERSONNES nommées trouvées (idéalement les décideurs : dirigeants officiels via Pappers/Societe.com, responsables marketing/digital via le site ou la presse). Pour chacune :
      - firstName, lastName
      - role : fonction si elle est explicitement indiquée dans une source (vide sinon)
      - email : UNIQUEMENT si une source montre clairement que cet email est CELUI DE CETTE PERSONNE (ex : page équipe avec l'email à côté du nom). Vide sinon. Ne devine JAMAIS prenom.nom@domaine.
      - phone : même règle stricte que l'email — uniquement si rattaché explicitement à la personne dans la source. Sinon vide (le mettre dans companyPhones si c'est un numéro général).
      - linkedin : URL LinkedIn publique seulement si elle apparaît dans tes résultats de recherche
      - source : libellé court de la source (ex : "site équipe", "mentions légales", "Pappers", "Societe.com", "presse: Les Échos", "résultat LinkedIn")
      - sourceUrl : l'URL EXACTE de la source — OBLIGATOIRE dès que tu donnes un email, un phone, ou un rôle non trivial. Si tu ne peux pas donner d'URL de source, alors tu ne donnes pas la coordonnée.
      - confidence : "high" = nom+rôle (et éventuelle coordonnée) vus verbatim et explicitement attribués dans une source citée ; "medium" = nom+rôle confirmés par recoupement de sources mais pas un seul document explicite ; "low" = signal faible (ne mets pas de coordonnée dans ce cas)
    Liste vide si aucune personne identifiable de façon fiable.
  - companyEmails : emails GÉNÉRIQUES de l'entreprise (contact@, info@, accueil@…) — pas ceux d'une personne
  - companyPhones : numéros de téléphone généraux de l'entreprise (standard, accueil)
  - companyAddress : adresse postale complète du siège si trouvée (Pappers/Societe.com/mentions légales), vide sinon

RÈGLE STRICTE — coordonnées : n'attribue un email/téléphone à une personne QUE si la source le rattache explicitement à elle, et cite alors sourceUrl. Un numéro qui traîne ailleurs sur le site va dans companyPhones, jamais collé à une personne « parce que ça pourrait être la sienne ». Mieux vaut un champ vide qu'une fausse coordonnée — c'est CRITIQUE : un faux numéro envoie le commercial vers quelqu'un d'autre.

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
    "approachAngles": ["..."],
    "contacts": [
      {{"firstName": "...", "lastName": "...", "role": "...", "email": "...", "phone": "...", "linkedin": "...", "source": "...", "sourceUrl": "...", "confidence": "high"}}
    ],
    "companyEmails": ["..."],
    "companyPhones": ["..."],
    "companyAddress": "..."
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

# Contact extraction.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_MAILTO_RE = re.compile(r'mailto:([^"\'?\s>]+)', re.IGNORECASE)
_TEL_RE = re.compile(r'tel:([^"\'?\s>]+)', re.IGNORECASE)
# French + international-ish phone patterns shown on sites.
_PHONE_RE = re.compile(
    r"(?<![\d/])(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{1,4}\)?[\s.\-]?){2,5}\d{2,4}(?![\d/])"
)
_LINKEDIN_RE = re.compile(
    r'https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|company)/[A-Za-z0-9\-_%]+',
    re.IGNORECASE,
)
# Junk emails to drop (image hashes, example.com, sentry, etc.).
_EMAIL_JUNK = re.compile(
    r"(@(?:sentry|example|domain|email|wixpress|sentry-cdn|godaddy)\.|"
    r"\.(png|jpe?g|gif|webp|svg|css|js|woff2?)$|^[0-9a-f]{16,}@)",
    re.IGNORECASE,
)


def _extract_contacts_raw(pages: list[tuple[str, str, dict]], site_domain: str) -> dict:
    """Pull emails / phones / LinkedIn URLs from the fetched HTML. Returns a
    dict the prompt can show the LLM so it can attribute them to people."""
    emails: set[str] = set()
    phones: set[str] = set()
    linkedins: set[str] = set()
    per_page: list[str] = []
    bare_domain = site_domain.split(":")[0].lower().lstrip("www.")
    for page_url, html, _ in pages:
        page_emails: set[str] = set()
        for m in _MAILTO_RE.finditer(html):
            e = m.group(1).strip().lower()
            if "@" in e and not _EMAIL_JUNK.search(e):
                page_emails.add(e)
        for m in _EMAIL_RE.finditer(html):
            e = m.group(0).strip().lower()
            if not _EMAIL_JUNK.search(e):
                page_emails.add(e)
        page_phones: set[str] = set()
        for m in _TEL_RE.finditer(html):
            v = re.sub(r"[^\d+]", "", m.group(1))
            if 7 <= len(re.sub(r"\D", "", v)) <= 15:
                page_phones.add(m.group(1).strip())
        # also scan visible text for phone-looking sequences (conservative:
        # require a separator or a leading + so we don't grab bare digit runs).
        vis = _visible_text(html)
        for m in _PHONE_RE.finditer(vis):
            raw = m.group(0).strip()
            digits = re.sub(r"\D", "", raw)
            has_sep = bool(re.search(r"[\s.\-()]", raw)) or raw.startswith("+")
            if has_sep and 9 <= len(digits) <= 13:
                page_phones.add(raw)
        page_links = {m.group(0) for m in _LINKEDIN_RE.finditer(html)}
        emails |= page_emails
        phones |= page_phones
        linkedins |= page_links
        if page_emails or page_phones or page_links:
            bits = []
            if page_emails:
                bits.append("emails: " + ", ".join(sorted(page_emails)[:15]))
            if page_phones:
                bits.append("téléphones: " + ", ".join(sorted(page_phones)[:10]))
            if page_links:
                bits.append("linkedin: " + ", ".join(sorted(page_links)[:10]))
            per_page.append(f"{page_url} → " + " ; ".join(bits))
    # Prefer emails on the company's own domain (more likely real contacts).
    domain_emails = sorted(e for e in emails if bare_domain in e)
    other_emails = sorted(e for e in emails if bare_domain not in e)
    return {
        "domainEmails": domain_emails[:25],
        "otherEmails": other_emails[:15],
        "phones": sorted(phones)[:15],
        "linkedins": sorted(linkedins)[:15],
        "perPage": per_page[:12],
    }


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

    contacts_raw = _extract_contacts_raw(pages, domain)
    cr_parts: list[str] = []
    if contacts_raw["domainEmails"]:
        cr_parts.append("Emails sur le domaine : " + ", ".join(contacts_raw["domainEmails"]))
    if contacts_raw["otherEmails"]:
        cr_parts.append("Autres emails vus : " + ", ".join(contacts_raw["otherEmails"]))
    if contacts_raw["phones"]:
        cr_parts.append("Téléphones vus : " + ", ".join(contacts_raw["phones"]))
    if contacts_raw["linkedins"]:
        cr_parts.append("LinkedIn vus : " + ", ".join(contacts_raw["linkedins"]))
    if contacts_raw["perPage"]:
        cr_parts.append("Par page :\n  " + "\n  ".join(contacts_raw["perPage"]))
    contacts_raw_text = "\n".join(cr_parts) if cr_parts else "(aucune coordonnée trouvée automatiquement sur le site)"

    prompt = _TEMPLATE.format(
        url=url,
        domain=domain,
        titles="\n".join(titles) or "(aucun)",
        metas="\n".join(metas) or "(aucune)",
        excerpt=excerpt or "(texte indisponible)",
        stack_summary=_stack_summary(stack),
        contacts_raw=contacts_raw_text,
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
        persona = ProspectPersona.model_validate(raw)
    except Exception as e:
        logger.debug("Bad persona payload: %s", e)
        return ProspectPersona()
    # Safety net: if a contact carries an email/phone but no source URL, the
    # attribution is unverified — strip the coordinate (move generic ones to
    # the company-level lists) and downgrade confidence.
    moved_emails: list[str] = list(persona.companyEmails)
    moved_phones: list[str] = list(persona.companyPhones)
    cleaned: list = []
    for c in persona.contacts:
        if (c.email or c.phone) and not (c.sourceUrl or "").strip():
            if c.email and c.email not in moved_emails:
                moved_emails.append(c.email)
            if c.phone and c.phone not in moved_phones:
                moved_phones.append(c.phone)
            c = c.model_copy(update={
                "email": "", "phone": "",
                "confidence": "low" if c.confidence == "high" else c.confidence,
            })
        cleaned.append(c)
    return persona.model_copy(update={
        "contacts": cleaned,
        "companyEmails": moved_emails,
        "companyPhones": moved_phones,
    })


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
