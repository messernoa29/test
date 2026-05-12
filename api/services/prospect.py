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
from urllib.parse import quote_plus, urljoin, urlparse

import httpx

from api.models import (
    DetectedTech,
    ProspectCompanyIdentity,
    ProspectParentCompany,
    ProspectParentContact,
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
    "/l-equipe", "/lequipe", "/team-members", "/people", "/about/people",
    "/a-propos", "/a-propos/", "/about", "/about/", "/about-us",
    "/agence", "/notre-agence", "/l-agence", "/lagence", "/qui-sommes-nous", "/notre-histoire",
    "/mentions-legales", "/mentions-legales/", "/legal", "/legal-notice", "/imprint",
]
_MAX_EXTRA_PAGES = 9
_MAX_TEXT_EXCERPT = 12000


_SYSTEM = (
    "Tu es un analyste commercial senior qui prépare des fiches prospect avant "
    "des rendez-vous de prospection B2B. Tu fais un vrai travail de recherche : "
    "tu pars de ce qui est réellement observable sur le site web ET d'une "
    "recherche web ciblée (annuaires légaux, presse, profils publics). RÈGLE "
    "ABSOLUE : tu n'inventes rien et tu ne devines aucune coordonnée. Si une "
    "information est inconnue, tu laisses la chaîne vide \"\" ou null — jamais "
    "de supposition présentée comme un fait.\n"
    "RÈGLE RÔLE : le champ `role` = la FONCTION de la personne (ex : « directrice "
    "de l'agence », « responsable commercial », « CEO »). « Directeur·rice de la "
    "publication », « éditeur du site », « responsable de la rédaction », "
    "« hébergeur » sont des MENTIONS LÉGALES, pas des intitulés de poste. Mais "
    "en pratique, sur un petit site, le « directeur de la publication » et/ou le "
    "représentant légal au RCS est presque toujours le ou la dirigeant·e : si "
    "c'est la seule info que tu as sur cette personne, mets role = « Dirigeant·e "
    "(d'après mentions légales / RCS) » plutôt que de laisser vide ou d'inventer "
    "un titre précis. Si une autre source (page équipe, signature « X, [poste] », "
    "article, LinkedIn public) donne un poste explicite, utilise-le directement. "
    "N'écris jamais littéralement « directeur de la publication » comme `role`.\n"
    "RÈGLE COORDONNÉES : un email ou un téléphone ne peut être attribué à une "
    "PERSONNE que si une source montre explicitement « cette coordonnée "
    "appartient à cette personne » (page équipe avec email/ligne directe à "
    "côté du nom, signature, carte de visite publiée…). Dans ce cas, sourceUrl "
    "est OBLIGATOIRE. Ne JAMAIS rattacher à une personne un numéro/email qui "
    "figure ailleurs sur le site sans lien explicite — mets-le plutôt dans "
    "companyEmails/companyPhones. Ne JAMAIS deviner un email type "
    "prenom.nom@domaine. En cas de doute : champ vide. Cherche activement les "
    "téléphones DIRECTS des personnes nommées (pages équipe détaillées, "
    "signatures de communiqués) mais ne les invente jamais.\n"
    "RÈGLE PERSONNES — D'ABORD LE SITE, ET SOIS GÉNÉREUX : ta priorité absolue "
    "est de lister TOUTES les personnes nommées sur le site lui-même — page "
    "« équipe / notre équipe / about », signatures, mentions légales du site, "
    "blog (auteurs), pages projets. Chaque membre cité = un contact dans la "
    "liste, AVEC son nom et son rôle tel qu'affiché. Ces personnes-là, tu les "
    "inclus toujours (confidence \"high\" ou \"medium\") — pas besoin de "
    "vérification supplémentaire pour quelqu'un qui figure sur le site officiel "
    "de l'entreprise. Ne renvoie JAMAIS une liste vide si le site nomme des "
    "gens : ce serait une erreur. Vise l'exhaustivité (5, 10, 15 personnes si "
    "le site les nomme), décideurs en tête puis opérationnels.\n"
    "RÈGLE PERSONNES — LE RCS NE FAIT QUE COMPLÉTER : Pappers/Societe.com et la "
    "presse servent à AJOUTER des décideurs que le site ne nomme pas, et à "
    "confirmer des rôles. Mais une personne trouvée UNIQUEMENT au registre "
    "légal et totalement absente du site / de la presse / des extraits LinkedIn "
    "(donc juste « représentant légal » sur Pappers, rien d'autre) : ne "
    "l'inclus PAS — c'est souvent un homonyme, un ancien dirigeant, un "
    "président de holding, ou la mauvaise société. En cas de doute sur "
    "l'identité d'une personne (homonymes possibles), garde quand même la "
    "personne du SITE et écarte celle qui ne vient que du registre.\n"
    "RÈGLE HOMONYMES / MANDATS : pour une personne nommée, si tu sais qu'elle "
    "est aussi rattachée publiquement à d'autres entreprises, liste-le dans "
    "otherAffiliations. Une coordonnée vue sur le site d'une AUTRE de ses "
    "sociétés ne se rattache pas ici.\n"
    "RÈGLE SOURCEURL : ne cite JAMAIS une URL que tu n'as pas réellement vue "
    "dans tes résultats de recherche ou en parcourant le site. Pas d'URL "
    "« plausible » reconstruite à la main (ex : deviner /equipe/jean-dupont). "
    "Si tu n'as pas l'URL exacte d'une source fiable, mets sourceUrl vide et "
    "n'affirme pas la coordonnée. Préfère l'URL de la page d'index "
    "(ex : la page « équipe ») si tu n'as pas l'URL profonde exacte.\n"
    "RÈGLE GROUPE / MAISON-MÈRE : cherche si l'entreprise appartient à un "
    "groupe / a une société mère / a été rachetée (Pappers et Societe.com "
    "indiquent les actionnaires personnes morales et le groupe ; les mentions "
    "légales et les communiqués aussi). Si oui : donne le nom du groupe, la "
    "nature du lien (filiale, marque, rachat + année…), et les dirigeants ou "
    "contacts connus de ce groupe (PDG, directeur général, etc.) avec leur "
    "source. Mêmes règles strictes : rien d'inventé, sourceUrl réel.\n"
    "SOURCES À UTILISER (recherche web) : annuaires légaux (Pappers, "
    "Societe.com, Infogreffe — fiables pour raison sociale, dirigeants "
    "officiels, actionnaires / groupe, date de création, adresse du siège) ; "
    "le site de l'entreprise (pages équipe / contact / mentions légales — "
    "priorité pour rattacher une coordonnée à une personne) ; articles de "
    "presse / interviews / communiqués (pour confirmer des rôles explicites "
    "« X, directeur marketing de … » et les opérations de rachat) ; résultats "
    "LinkedIn PUBLICS tels qu'ils apparaissent dans la recherche (pour "
    "confirmer nom+rôle UNIQUEMENT — jamais de numéro/email privé, et tu "
    "n'ouvres pas les pages linkedin.com).\n"
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

Utilise web_search de façon INTENSIVE. Tu DOIS faire AU MOINS ces recherches avant de finaliser (plusieurs requêtes, pas une seule) :
1. site:linkedin.com/in "<raison sociale>" — puis idem avec le nom commercial, puis avec le nom du groupe/maison-mère s'il y en a un. Les extraits LinkedIn publics renvoyés te donnent des noms + postes d'employés actuels. (Tu n'ouvres pas linkedin.com et tu ne reprends jamais de numéro/email privé — uniquement nom + rôle visibles dans le snippet.)
2. "<raison sociale> équipe" / "<raison sociale> notre équipe" / "<raison sociale> qui sommes-nous" / "<nom commercial> team" — membres de l'équipe que le site ne montre pas directement.
3. "<raison sociale> directeur" / "... fondateur" / "... CEO" / "... responsable commercial" / "... gérant" / "<prénom seul vu sur le site> <raison sociale>" — confirmer/compléter des postes réels via articles, interviews, Codeur, Malt, communiqués. Si le site ne donne qu'un PRÉNOM (ex : « Simon » sur un widget de RDV), cherche activement « Simon <raison sociale> » et « Simon <raison sociale> linkedin » pour retrouver son nom de famille et son poste — et s'il y a plusieurs candidats, choisis le mieux sourcé MAIS signale le doute dans `note`.
4. "{domain} Pappers" / "{domain} Societe.com" / "<raison sociale> Infogreffe" — dirigeants officiels, ACTIONNAIRES / société mère, date de création, adresse du siège, raison sociale.
5. "<prénom nom> Pappers" / "<prénom nom> dirigeant" pour CHAQUE personne trouvée — vérifier que c'est la bonne personne (pas un homonyme), repérer ses autres mandats (→ otherAffiliations).
6. "<raison sociale> rachat" / "... groupe" / "... filiale de" — détecter une maison-mère / un rachat, puis "<nom du groupe> PDG / dirigeants" pour ses contacts.
Si le site n'a quasiment aucun nom (site vitrine Webflow/Wix…), la recherche web — surtout l'étape 1 (linkedin/in) — est ta source PRINCIPALE pour les personnes : ne te contente jamais du seul nom des mentions légales.

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
  - parentCompany : société mère / groupe auquel l'entreprise appartient, OU null si elle est indépendante / aucune info fiable. Si renseigné :
      - name : nom du groupe / de la société mère
      - relation : nature du lien en quelques mots (« filiale à 100 % », « racheté en 2022 par … », « marque du groupe … », « participation majoritaire de … »)
      - website : site du groupe si connu (vide sinon)
      - location : ville/pays du groupe (vide sinon)
      - notes : 1-2 phrases sur le groupe (taille, autres marques/filiales, secteur)
      - source / sourceUrl : libellé court + URL EXACTE de la source (Pappers, Societe.com, communiqué, page « le groupe »…)
      - contacts : dirigeants ou contacts connus du GROUPE (PDG, directeur général, directeur du développement…), chacun : firstName, lastName, role (fonction dans le groupe), source, sourceUrl (URL exacte ou vide). Liste vide si aucun connu de façon fiable.
- persona :
  - likelyContactRoles : 1-3 rôles probables à contacter (ex : "Dirigeant·e", "Responsable marketing", "Responsable e-commerce", "DSI") selon la taille et le secteur
  - likelyPriorities : 2-4 priorités / douleurs probables de ce décideur
  - approachAngles : 2-4 accroches de prospection PERSONNALISÉES, ancrées sur ce qui a réellement été observé sur le site
  - contacts : liste de TOUTES les PERSONNES nommées — commence IMPÉRATIVEMENT par tous les gens nommés sur le SITE (page équipe / notre équipe / about, signatures, mentions légales du site, auteurs du blog, pages projets). Chaque membre cité sur le site = un contact ici (confidence "high"/"medium"), sans vérification supplémentaire. Ne renvoie PAS une liste vide si le site nomme des gens. Ajoute ensuite, en complément, les décideurs trouvés via Pappers/Societe.com/presse/LinkedIn que le site ne nomme pas. N'ajoute PAS une personne qui n'existe QUE dans le registre légal et nulle part ailleurs. Vise l'exhaustivité (5, 10, 15+ si le site les nomme), décideurs en tête puis opérationnels. Pour chacune :
      - firstName, lastName
      - role : sa FONCTION professionnelle réelle si une source la décrit explicitement (« directrice de l'agence », « responsable commercial », « DAF »…). VIDE si la seule info est une mention légale (« directeur·rice de la publication », « responsable de la rédaction », « éditeur du site »…) — ce ne sont PAS des postes. RAPPEL : une personne trouvée UNIQUEMENT au registre légal (Pappers/Societe.com) et absente du site n'apparaît PAS dans la liste — ne l'invente pas un rôle pour la garder. Si elle est gardée parce que la fiche légale concorde ET qu'une autre source la confirme, mais que cette confirmation reste faible : « <Titre> (mention RCS) » + confidence "low".
      - note : avertissement éventuel sur ce contact. Exemples : « nom de famille déduit de la recherche web — à confirmer ; autre hypothèse : Simon Frayssines », « rôle d'après mentions légales / RCS — à confirmer », « confirmé via le site mais aussi représentant légal au RCS ». Vide si rien à signaler. METS TOUJOURS une note quand le nom de famille ou le rôle vient d'une déduction et pas d'une source qui nomme la personne explicitement avec l'entreprise.
      - email : UNIQUEMENT si une source montre clairement que cet email est CELUI DE CETTE PERSONNE (ex : page équipe avec l'email à côté du nom). Vide sinon. Ne devine JAMAIS prenom.nom@domaine.
      - phone : cherche activement la ligne DIRECTE de la personne (page équipe détaillée, signature de communiqué). Ne la renseigne QUE si la source la rattache explicitement à cette personne. Sinon vide (un numéro général va dans companyPhones, jamais collé à une personne).
      - linkedin : URL LinkedIn publique seulement si elle apparaît dans tes résultats de recherche
      - otherAffiliations : autres entreprises / mandats publics de cette personne (« gérant de … », « président de … », « fondateur de … »), liste vide si aucune connue. Sert à repérer les homonymes et les mandats croisés.
      - source : libellé court de la source (ex : "site équipe", "mentions légales", "Pappers", "Societe.com", "presse: Les Échos", "résultat LinkedIn")
      - sourceUrl : l'URL EXACTE de la source — OBLIGATOIRE dès que tu donnes un email, un phone, ou un rôle non trivial. Si tu ne peux pas donner d'URL de source, alors tu ne donnes pas la coordonnée.
      - confidence : "high" = nom+rôle (et éventuelle coordonnée) vus verbatim et explicitement attribués dans une source citée ; "medium" = nom+rôle confirmés par recoupement de sources mais pas un seul document explicite ; "low" = signal faible (ne mets pas de coordonnée dans ce cas)
    Liste vide UNIQUEMENT si le site ne nomme personne ET qu'aucune source ne donne de nom — ce qui est rare.
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
    "valueProposition": "...",
    "parentCompany": null
  }},
  "persona": {{
    "likelyContactRoles": ["..."],
    "likelyPriorities": ["..."],
    "approachAngles": ["..."],
    "contacts": [
      {{"firstName": "...", "lastName": "...", "role": "...", "email": "...", "phone": "...", "linkedin": "...", "otherAffiliations": ["..."], "note": "", "source": "...", "sourceUrl": "...", "confidence": "high"}}
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
        persona = _add_linkedin_search(persona, identity)
        identity, persona = _verify_source_urls(identity, persona)
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
        seen_urls = {_norm_url(home[0])}

        def try_fetch(target: str) -> None:
            if len(out) > _MAX_EXTRA_PAGES:
                return
            page = _get(client, target)
            if page is None:
                return
            key = _norm_url(page[0])
            if key in seen_urls:
                return
            seen_urls.add(key)
            out.append(page)

        # 1) Links discovered in the home HTML that look like team/about/contact
        #    pages — this beats blind path-probing on real sites.
        for href in _discover_people_links(home[1], home[0])[:8]:
            if len(out) > _MAX_EXTRA_PAGES:
                break
            try_fetch(href)
        # 2) Fallback: blind-probe well-known paths for the ones we still miss.
        for path in _KEY_PATHS:
            if len(out) > _MAX_EXTRA_PAGES:
                break
            try_fetch(urljoin(origin + "/", path.lstrip("/")))
    finally:
        client.close()
    return out


def _norm_url(u: str) -> str:
    """Normalise a URL for dedup: drop scheme case, fragment, trailing slash."""
    p = urlparse(u.strip())
    path = (p.path or "/").rstrip("/") or "/"
    return f"{p.netloc.lower()}{path}?{p.query}" if p.query else f"{p.netloc.lower()}{path}"


_PEOPLE_HREF_RE = re.compile(
    r"(equipe|equipes|team|teams|notre-equipe|our-team|about|a-propos|apropos|"
    r"qui-sommes-nous|agence|notre-agence|l-agence|people|staff|trombinoscope|"
    r"contact|nous-contacter|contactez|mentions-legales|legal|imprint|fondateur|"
    r"founders?|leadership|management|direction)",
    re.IGNORECASE,
)
_HREF_RE = re.compile(r'href=["\']([^"\'#?]+)', re.IGNORECASE)


def _discover_people_links(home_html: str, home_url: str) -> list[str]:
    """Absolute, same-host URLs found in the home page whose path/anchor looks
    like a team / about / contact / legal page. Deduped, order-preserving."""
    base = urlparse(home_url)
    host = base.netloc.lower()
    found: list[str] = []
    seen: set[str] = set()
    for m in _HREF_RE.finditer(home_html or ""):
        raw = m.group(1).strip()
        if not raw or raw.startswith(("mailto:", "tel:", "javascript:", "data:")):
            continue
        absu = urljoin(home_url, raw)
        p = urlparse(absu)
        if p.scheme not in ("http", "https") or p.netloc.lower() != host:
            continue
        path = p.path or "/"
        if path in ("", "/"):
            continue
        if not _PEOPLE_HREF_RE.search(path):
            continue
        key = _norm_url(absu)
        if key in seen:
            continue
        seen.add(key)
        found.append(absu)
    return found


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
            max_tokens=16000,
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
    logger.info(
        "Prospect enrich for %s: stop=%s, %d contact(s), parent=%s",
        domain, response.stop_reason, len(persona.contacts),
        bool(identity.parentCompany),
    )
    if not persona.contacts:
        logger.warning(
            "Prospect enrich for %s returned 0 contacts (stop=%s). Raw persona keys=%s",
            domain, response.stop_reason,
            list(payload.get("persona").keys()) if isinstance(payload.get("persona"), dict) else None,
        )
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
    # Drop an empty parentCompany shell (no name → nothing to show).
    pc = identity.parentCompany
    if pc is not None and not (pc.name or "").strip():
        identity = identity.model_copy(update={"parentCompany": None})
    elif pc is not None:
        scrubbed_contacts = [
            c.model_copy(update={"role": _scrub_legal_role(c.role)})
            for c in pc.contacts
        ]
        identity = identity.model_copy(
            update={"parentCompany": pc.model_copy(update={"contacts": scrubbed_contacts})}
        )
    return identity


# Legal-mention phrases that French sites are required to display but which
# are NOT job titles — never keep them as a contact's `role`.
_LEGAL_MENTION_ROLE_RE = re.compile(
    r"(directeur|directrice|dir\.?)\s+(de\s+(la\s+)?)?publication"
    r"|responsable\s+de\s+(la\s+)?(publication|r[ée]daction)"
    r"|[ée]diteur(\s+du\s+site)?\b"
    r"|h[ée]bergeur\b"
    r"|webmaster\b",
    re.IGNORECASE,
)


def _scrub_legal_role(role: str) -> str:
    r = (role or "").strip()
    if not r:
        return ""
    return "" if _LEGAL_MENTION_ROLE_RE.search(r) else r


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
    # the company-level lists) and downgrade confidence. Also scrub legal-
    # mention "roles" (directeur de la publication, etc.).
    moved_emails: list[str] = list(persona.companyEmails)
    moved_phones: list[str] = list(persona.companyPhones)
    cleaned: list = []
    for c in persona.contacts:
        updates: dict = {}
        scrubbed = _scrub_legal_role(c.role)
        if scrubbed != (c.role or ""):
            updates["role"] = scrubbed
        if (c.email or c.phone) and not (c.sourceUrl or "").strip():
            if c.email and c.email not in moved_emails:
                moved_emails.append(c.email)
            if c.phone and c.phone not in moved_phones:
                moved_phones.append(c.phone)
            updates["email"] = ""
            updates["phone"] = ""
            updates["confidence"] = "low" if c.confidence == "high" else c.confidence
        if updates:
            c = c.model_copy(update=updates)
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


def _add_linkedin_search(
    persona: ProspectPersona, identity: ProspectCompanyIdentity
) -> ProspectPersona:
    """Attach a pre-filled LinkedIn people-search URL to each named contact.
    Search by full name when we have a surname (adding the company name would
    return zero results); if only a first name is known, disambiguate with the
    company name. We don't fetch anything here."""
    company = (identity.name or "").strip()
    out: list = []
    for c in persona.contacts:
        first = (c.firstName or "").strip()
        last = (c.lastName or "").strip()
        full = " ".join(b for b in [first, last] if b).strip()
        if not full:
            out.append(c)
            continue
        keywords = full if last else " ".join(b for b in [first, company] if b).strip()
        url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(keywords)}"
        out.append(c.model_copy(update={"linkedinSearchUrl": url}))
    return persona.model_copy(update={"contacts": out})


def _url_status(client: httpx.Client, url: str) -> Optional[int]:
    """Return the HTTP status of `url` (after redirects), or None if unreachable
    / malformed. HEAD first, ranged GET as a fallback."""
    u = (url or "").strip()
    if not u or not u.lower().startswith(("http://", "https://")):
        return None
    try:
        resp = client.head(u)
        if resp.status_code in (403, 405, 501):
            resp = client.get(u, headers={"Range": "bytes=0-2048"})
    except httpx.HTTPError:
        try:
            resp = client.get(u, headers={"Range": "bytes=0-2048"})
        except httpx.HTTPError as e:
            logger.debug("URL check failed for %s: %s", u, e)
            return None
    return resp.status_code


def _check_url_alive(client: httpx.Client, url: str) -> Optional[bool]:
    """True if the URL responds < 400, False if it 404s / unreachable, None if
    we can't tell (malformed URL). We never *remove* anything based on this —
    it only powers a ⚠️ hint in the UI."""
    if not (url or "").strip() or not url.strip().lower().startswith(("http://", "https://")):
        return None
    status = _url_status(client, url)
    if status is None:
        return False
    return status < 400


def _linkedin_url_dead(client: httpx.Client, url: str) -> bool:
    """LinkedIn returns 999 / login walls for bots, so we only treat a *hard*
    404/410 as a confirmed dead profile URL (worth dropping)."""
    status = _url_status(client, url)
    return status in (404, 410)


def _verify_source_urls(
    identity: ProspectCompanyIdentity, persona: ProspectPersona
) -> tuple[ProspectCompanyIdentity, ProspectPersona]:
    """HEAD/GET every sourceUrl the LLM cited; tag each with sourceUrlOk.
    Nothing is removed — a dead link just gets a ⚠️ in the UI."""
    headers = {"User-Agent": _USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7"}
    try:
        client = httpx.Client(
            headers=headers, timeout=8.0, follow_redirects=True, verify=False
        )
    except Exception as e:
        logger.debug("source URL verifier: client init failed: %s", e)
        return identity, persona
    cache: dict[str, Optional[bool]] = {}

    def check(url: str) -> Optional[bool]:
        key = (url or "").strip()
        if key in cache:
            return cache[key]
        cache[key] = _check_url_alive(client, key)
        return cache[key]

    try:
        # contacts: check sourceUrl + drop a LinkedIn profile URL that hard-404s
        new_contacts = []
        for c in persona.contacts:
            upd: dict = {}
            if (c.sourceUrl or "").strip():
                upd["sourceUrlOk"] = check(c.sourceUrl)
            if (c.linkedin or "").strip() and _linkedin_url_dead(client, c.linkedin):
                upd["linkedin"] = ""
            new_contacts.append(c.model_copy(update=upd) if upd else c)
        persona = persona.model_copy(update={"contacts": new_contacts})
        # parent company + its contacts
        pc = identity.parentCompany
        if pc is not None:
            pc_contacts = [
                c.model_copy(update={"sourceUrlOk": check(c.sourceUrl)})
                if (c.sourceUrl or "").strip() else c
                for c in pc.contacts
            ]
            pc = pc.model_copy(update={
                "contacts": pc_contacts,
                "sourceUrlOk": check(pc.sourceUrl) if (pc.sourceUrl or "").strip() else pc.sourceUrlOk,
            })
            identity = identity.model_copy(update={"parentCompany": pc})
    finally:
        client.close()
    return identity, persona


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
