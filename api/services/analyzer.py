"""Step 2 of the audit pipeline: analyze crawl data and produce AuditResult.

Split into multiple Claude calls so we never rely on a single 12K-token
response holding up. A big site (20+ pages) otherwise truncates mid-way.

Flow:
1. OVERVIEW  — 6 axis scores, findings, quick wins, global verdict.
2. PAGES     — page-by-page details, paginated in batches so each response
               stays well under max_tokens.
3. MISSING   — strategic pages absent from the site.

Results from the three stages are merged into a single AuditResult.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from typing import Callable, Optional

from api.models import AuditResult, CompetitorReport, CrawlData, CrawlPage
from api.services.llm import LLMResponse, get_llm_client

logger = logging.getLogger(__name__)

PAGE_BATCH_SIZE = 10  # pages per PAGES call — fewer round-trips, ~9-12K tokens
INTER_CALL_DELAY_S = 2.5
# Hard ceiling on per-page analysis: above this many pages we still analyse
# the most important N in detail (the technical crawl + link graph already
# cover all of them); avoids 9+ LLM round-trips on the free tier.
MAX_PAGES_DETAILED = 30


_SYSTEM = """Tu es un consultant senior en audit web professionnel, spécialisé SEO technique, contenu E-E-A-T, UX, performance, sécurité et visibilité AI (GEO).
Méthodologie inspirée du framework open-source AgriciDaniel/claude-seo (MIT).

## Pondération des axes (score global = moyenne pondérée)
- Technical SEO      22%  (crawlability, indexability, security, URLs, mobile, CWV, JS rendering, IndexNow, AI crawlers)
- Content            23%  (E-E-A-T, thin content, lisibilité, originalité, fraîcheur, AI citation readiness)
- On-Page SEO        20%  (titles, meta, H1-Hn, internal linking, cannibalisation)
- Schema / LD-JSON   10%  (détection, validation, opportunités)
- Performance (CWV)  10%  (LCP <2.5s, INP <200ms, CLS <0.1)
- AI Search (GEO)    10%  (citability 134-167 mots, llms.txt, crawlers AI autorisés)
- Images              5%  (alt text, formats modernes, taille)

## Règles métier à jour (février 2026) — NE PAS conseiller ce qui est déprécié
- INP a remplacé FID le 12 mars 2024 — FID totalement retiré. Ne JAMAIS mentionner FID.
- Mobile-first indexing 100% en place depuis 5 juil 2024. Googlebot utilise exclusivement le user-agent mobile.
- HowTo rich results retirés en septembre 2023 — ne pas recommander.
- FAQPage rich results restreint aux sites gouvernement/santé depuis août 2023 — ne pas recommander aux sites commerciaux.
- SpecialAnnouncement déprécié 31 juillet 2025.
- CourseInfo, EstimatedSalary, LearningVideo, ClaimReview, VehicleListing retirés juin 2025.
- Helpful Content System fusionné dans Core algorithm en mars 2024 — ne plus parler de HCU en tant que classifier séparé.
- JavaScript rendering (guidance Google décembre 2025) : canonicals/noindex/schema doivent être dans le HTML initial, pas injectés par JS.
- Google AI Mode lancé mai 2025 dans 180+ pays, expérience conversationnelle sans liens bleus — citation AI = seule visibilité.

## AI crawlers à connaître (robots.txt)
GPTBot, OAI-SearchBot, ChatGPT-User (OpenAI) ; ClaudeBot, anthropic-ai (Anthropic) ; PerplexityBot ; Google-Extended (Gemini training, n'affecte PAS Google Search) ; CCBot (Common Crawl) ; Bytespider (ByteDance) ; cohere-ai.
Bloquer Google-Extended n'affecte PAS le référencement Google. Bloquer GPTBot n'empêche PAS ChatGPT de citer via ChatGPT-User.

## Citability pour AI search (GEO)
- Longueur optimale d'un passage cité par un LLM : 134-167 mots.
- Réponse directe dans les 40-60 premiers mots d'une section.
- Hn sous forme de question (matche les requêtes).
- Statistiques/faits avec attribution source.
- Brand mentions (Wikipedia, Reddit, YouTube) > backlinks pour la citation AI (corrélation 3× plus forte, étude Ahrefs déc 2025).

## E-E-A-T (Quality Rater Guidelines, mise à jour sept 2025)
- Experience: recherche originale, case studies, photos/vidéos first-hand.
- Expertise: auteur identifié, credentials, profondeur technique.
- Authoritativeness: citations externes, mentions presse, reconnaissance industrie.
- Trustworthiness: contact visible, RGPD, HTTPS, date de publication/mise à jour.
- Attention AI content: générique/répétitif/sans attribution = pénalisé.

## Discipline anti-hallucination (règle "INSUFFICIENT DATA")
Si un axe ne peut être évalué avec < 4/7 facteurs observables (score factuel impossible), tu l'indiques explicitement dans le verdict : "Évaluation partielle — données insuffisantes sur [facteurs]." Tu ne remplis PAS un score arbitraire pour combler.

## Règles de sortie (strictes)
1. Tu ne retournes QUE le bloc XML demandé, sans aucun texte avant ni après.
2. Tu termines TOUJOURS ta réponse par la balise fermante attendue.
3. Descriptions, verdicts, recommendations : concis (1-3 phrases), factuel, pas de hype."""


_OVERVIEW_TEMPLATE = """Audit de {domain} — {page_count} pages crawlées directement en HTTP (données exhaustives, ne PAS re-crawler).
web_search autorisé uniquement pour vérifier un élément externe (volume de recherche, règle réglementaire, présence d'un concurrent).

Produis UNIQUEMENT la partie "overview" — les 6 axes + scores + quick wins + verdict global. La liste détaillée par page sera demandée séparément.

**IMPÉRATIF ABSOLU** : tu produis exactement 6 sections, ni plus ni moins. Les valeurs `section` autorisées sont STRICTEMENT : `security`, `seo`, `ux`, `content`, `performance`, `business`.
- Les sujets "images", "schema", "AI search / GEO", "local", "technical", "on-page" n'ont PAS de section propre : intègre leurs findings dans l'une des 6 sections existantes (ex: images → content ou performance, schema → seo, AI search → business, local → business, technical → seo, on-page → seo).
- Si un de ces sujets est critique sur le site, crée un finding distinct dans la section d'accueil avec un `title` explicite (ex: "Images non optimisées").

## Les 6 axes à produire (valeurs `section` imposées)

### 1. security — Sécurité & conformité
À vérifier: HTTPS + redirection 301, certificat valide, mixed content, headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy), HSTS preload, RGPD (bannière cookies, politique confidentialité), formulaires protégés, traitement des données.

### 2. seo — SEO technique + on-page
À vérifier: robots.txt (+ gestion crawlers AI en 2026), sitemap.xml référencé, canonicals cohérents, noindex intentionnels, duplicate content, cannibalisation inter-pages (title/H1 identiques), titles/meta longueurs, hiérarchie Hn, internal linking, URLs propres, redirects chains, hreflang si multilingue, index bloat.

### 3. ux — Expérience utilisateur
À vérifier: navigation claire, CTA visibles, mobile-first (touch targets 48×48px, font 16px min, viewport meta), pas de scroll horizontal, parcours de conversion, charge cognitive, accessibilité (WCAG: contraste, alt, ARIA, focus, labels).

### 4. content — Qualité & E-E-A-T
À vérifier: proposition de valeur claire, E-E-A-T (Experience/Expertise/Authoritativeness/Trust), auteurs identifiés, dates, sources, thin content (< seuil par type), lisibilité (Flesch cible 60-70 audience générale — rappel: pas un signal de ranking direct Google), fraîcheur, citabilité AI (passages 134-167 mots, réponse en 40-60 premiers mots, Hn en questions, tables/listes).

### 5. performance — Core Web Vitals + technique perf
À vérifier: LCP <2.5s, INP <200ms (remplace FID retiré), CLS <0.1, images (formats WebP/AVIF, lazy-loading, dimensions, alt), scripts tiers, CSS/JS minifiés, CDN, compression Brotli/gzip, fonts préchargées. Si pas de CrUX réel: préciser "estimation, non field-data".

### 6. business — Conversion, local, AI search, opportunités
À vérifier: CTAs efficaces, lead magnet, preuves sociales chiffrées, tracking GA4 events, retargeting, schema.org (JSON-LD: Organization, LocalBusiness, Product, Article, Person selon page), SEO local (GBP, NAP consistency, schema LocalBusiness) si pertinent, visibilité AI (llms.txt présent, AI crawlers autorisés, citations possibles).

## Quotas de sortie (dimensionne selon la pertinence — PAS de remplissage uniforme)
- 3 à 6 findings par axe. Si axe sain → 2 findings + 1 finding "ok".
- description : 1 à 3 phrases (≤ 320 chars). DOIT contenir la PREUVE observée : l'URL exacte, la valeur mesurée, le compte, ou la balise concernée. Interdit : "le SEO peut être amélioré", "des optimisations sont possibles", "la performance n'est pas optimale". Obligatoire : "La page /contact n'a pas de <meta name=description> (vu dans le crawl)", "12 images sur 34 n'ont pas d'attribut alt", "Le title de /tarifs fait 78 caractères (max recommandé 60)".
- recommendation : 1 à 2 phrases (≤ 280 chars). Le RÉSULTAT attendu, chiffré si possible : "Réduire le title à ≤ 60 caractères → meilleur taux de clic SERP", pas "améliorer les titles".
- actions : 2 à 6 items, ≤ 180 chars chacun. CHAQUE action = une étape OPÉRATIONNELLE qu'on peut exécuter sans réfléchir. Format impératif. Inclure : le QUOI (élément précis), le OÙ (page/fichier/section CMS), et idéalement le NOUVEAU CONTENU proposé entre guillemets. Exemples valides :
  · "Sur /tarifs, remplacer le <title> actuel par : \\"Tarifs et formules — [Nom marque] | À partir de 29€/mois\\""
  · "Ajouter dans le <head> de toutes les pages : <link rel=\\"canonical\\" href=\\"[URL absolue de la page]\\">"
  · "Dans robots.txt, ajouter la ligne : Sitemap: https://exemple.com/sitemap.xml"
  · "Sur les 12 images sans alt listées plus haut, renseigner un alt descriptif (ex: pour hero.jpg → alt=\\"Équipe en réunion dans les bureaux de Paris\\")"
  Interdit : "optimiser les images", "revoir la structure", "améliorer le contenu", "ajouter des balises" (sans dire lesquelles ni où).
- RÈGLE D'OR : si tu écris un finding sans pouvoir donner d'actions concrètes derrière, c'est que tu n'as pas assez de données → ne l'écris pas, ou marque-le `severity: info` en disant explicitement "audit manuel requis : [quoi vérifier]".
- verdict d'axe : 1 phrase courte (style "Bon niveau, quelques améliorations ciblées" ou "À consolider — headers sécurité absents, RGPD partiel").
- quickWins : 4 à 8 items priorisés par ratio impact/effort. CHAQUE quick win = une action exécutable (pas un thème). "Ajouter meta description sur /contact, /faq, /tarifs" ✓ — "Travailler le SEO on-page" ✗.

## Enums (respect strict — ne pas inventer)
- severity : critical | warning | info | ok | missing   (PAS "improve")
- impact   : high | medium | low
- effort   : quick | medium | heavy                     (PAS "high"/"low")

## Scoring (0-100 par axe)
- 80-100 : excellent (peu/pas d'issues critiques)
- 60-79  : bon (qq quick wins)
- 40-59  : à consolider (issues structurelles)
- 20-39  : défaillant (plusieurs critiques)
- 0-19   : critique (bloquant pour le business)
globalScore = moyenne pondérée (voir pondérations dans le system prompt).

## Discipline (règle AgriciDaniel)
Si tu n'as pas assez de facteurs observables sur un axe (< 4/7) → dis-le dans le verdict ("Évaluation partielle — [facteurs]") plutôt que d'inventer un score. Tu peux toujours lister les findings observés.

## Données du crawl
{crawl_json}

{performance_block}

{schemas_block}

{link_graph_block}

{quality_block}

{technical_block}

{crawl_table_block}

## Sortie STRICTE (aucun texte hors balises)

<OVERVIEW_JSON>
{{
  "domain": "{domain}",
  "url": "{url}",
  "globalScore": 0,
  "globalVerdict": "...",
  "scores": {{
    "security": 0, "seo": 0, "ux": 0, "content": 0, "performance": 0, "business": 0
  }},
  "sections": [
    {{
      "section": "security",
      "title": "Sécurité",
      "score": 0,
      "verdict": "...",
      "findings": [
        {{
          "severity": "critical",
          "title": "...",
          "description": "...",
          "recommendation": "...",
          "actions": ["...", "..."],
          "impact": "high",
          "effort": "quick"
        }}
      ]
    }}
  ],
  "criticalCount": 0,
  "warningCount": 0,
  "quickWins": ["...", "...", "..."]
}}
</OVERVIEW_JSON>
"""


_PAGES_BATCH_TEMPLATE = """Analyse détaillée, page par page, du site {domain} (batch de {batch_count} URLs).

CONSIGNE ABSOLUE : produire UNE entrée dans `pages[]` pour CHACUNE des {batch_count} URLs listées. Pas de sélection, pas d'omission.

## Ce que tu vérifies par page

### Titre & meta
- Longueur title : idéal 50-60 chars (Google coupe ~65). Flagger <30 ou >70.
- Longueur meta description : idéal 150-160 chars. Flagger <70 ou >170.
- Title contient le mot-clé principal, différencié par page, pas stuffé.
- Meta description incite au clic, inclut un CTA ou un bénéfice.

### Hn / structure
- Un seul H1 par page, avec mot-clé, contextualisé (pas juste 2 mots).
- Hiérarchie Hn logique (H1 → H2 → H3, pas de saut).
- Headings en questions idéal pour AI citation.

### URL & canonique
- URL descriptive, hyphenée, < 100 chars.
- Pas de jargon interne (éviter "foodcamp", "cycle2", noms de code projets).
- Canonical self-referencing dans HTML initial (pas injecté par JS).

### Keywords (estimés depuis title + H1 + headings)
- targetKeywords : 3-6 requêtes que la page DEVRAIT cibler (déduit du métier + titre).
- presentKeywords : 3-6 expressions réellement visibles dans title/H1/Hn.
- missingKeywords : 3-6 expressions absentes mais critiques (ex: "RNCP", "prix", "CPF", "Paris" si école à Paris).

### Cannibalisation
- Compare titles/H1 entre URLs du batch et flag si ≥ 2 pages partagent title ou H1.

### Status de la page
- critical : bloquant (noindex accidentel, 404, title vide, redirection mauvaise, faute orthographe critique dans title, cannibalisation)
- warning  : plusieurs issues à fort impact (meta absente + H1 faible + Hn cassée)
- improve  : quelques améliorations ciblées (title trop court, KW manquants)
- ok       : page saine, rien de significatif à remonter

### Recommendation AVANT/APRÈS
Pour chaque page avec status ≠ ok, fournis `recommendation` avec l'état actuel + version recommandée :
- urlCurrent / titleCurrent / h1Current / metaCurrent
- url / title / h1 / meta (versions recommandées optimisées)
- actions : 3-5 étapes techniques concrètes

## Quotas
- Par page : 2 à 5 findings (pas de remplissage). Si page ok, 1-2 findings "ok" suffisent.
- Tous les textes ≤ 180 chars (title/description/recommendation) ou ≤ 140 chars (actions).
- Keywords : 3-6 items par liste.

## Enums (respect strict)
- status           : critical | warning | improve | ok     (PAS "info" ou autres)
- finding.severity : critical | warning | info | ok | missing   (PAS "improve")
- impact           : high | medium | low
- effort           : quick | medium | heavy                (PAS "high"/"low")

## Données du batch
{batch_json}

## Sortie STRICTE

<PAGES_JSON>
{{
  "pages": [
    {{
      "url": "...",
      "status": "critical",
      "title": "...",
      "titleLength": 0,
      "h1": "...",
      "metaDescription": null,
      "metaLength": 0,
      "targetKeywords": [],
      "presentKeywords": [],
      "missingKeywords": [],
      "findings": [
        {{ "severity": "critical", "title": "...", "description": "...", "impact": "high", "effort": "quick" }}
      ],
      "recommendation": {{
        "urlCurrent": "...",
        "titleCurrent": "...",
        "h1Current": "...",
        "metaCurrent": null,
        "url": "...",
        "title": "...",
        "h1": "...",
        "meta": "...",
        "actions": ["...", "..."]
      }}
    }}
  ]
}}
</PAGES_JSON>
"""


_MISSING_TEMPLATE = """À partir du crawl de {domain} ({page_count} pages), identifie les pages stratégiques MANQUANTES qui devraient exister pour :
- Capter des requêtes à fort volume non couvertes par les pages existantes
- Convertir davantage (financement, contact qualifié, comparaison vs concurrents, confiance)
- Répondre aux attentes E-E-A-T (page À propos détaillée, équipe, mentions presse)
- Couvrir les angles locaux (une landing page par ville pour SEO local) si pertinent
- Combler les gaps de visibilité AI (FAQ structurée, llms.txt en base de connaissances)

Tu peux utiliser web_search pour vérifier le volume mensuel estimé d'une requête (`estimatedSearchVolume`).

## Catégories d'opportunités à explorer
- **Pages locales** (SEO local) : /services-ville pour chaque ville desservie
- **Pages financement/prix/FAQ** (barrière d'entrée principale)
- **Pages preuve sociale** : cas clients, témoignages, diplômés/insertion
- **Pages comparatives** : "Notre solution vs [concurrent]" ou "X vs Y"
- **Pages topic cluster** : pillar page + sous-pages liées pour l'autorité thématique
- **Pages "À propos / Équipe / Pourquoi nous"** : critiques pour E-E-A-T et confiance
- **Pages lead magnet** : guide gratuit, webinar, quiz d'orientation

## Quotas
- 4 à 8 entrées, priorisées par ratio impact / effort de création.
- reason : 1 phrase (≤ 160 chars) qui explique pourquoi la page compte pour CE site.
- priority : high | medium | low (high = ROI très clair, low = nice-to-have).
- estimatedSearchVolume : entier, volume mensuel agrégé France (0 si non estimable).
- url : slug court, descriptif, commençant par `/` (ex: `/formation-cuisine-paris`).

## URLs existantes (à NE PAS re-suggérer, même en variantes proches)
{existing_urls}

## Sortie STRICTE

<MISSING_JSON>
{{
  "missingPages": [
    {{ "url": "/exemple-strategique", "reason": "...", "estimatedSearchVolume": 0, "priority": "high" }}
  ]
}}
</MISSING_JSON>
"""


# ---------------------------------------------------------------------------
# Public API


def _time_boxed(fn: Callable, timeout_s: float, label: str):
    """Run `fn` in a worker thread; return its result or None if it exceeds
    `timeout_s` or raises. The worker thread is left to finish on its own
    (we can't kill it) but the audit moves on."""
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn)
            return fut.result(timeout=timeout_s)
    except FuturesTimeout:
        logger.warning("Optional pass '%s' timed out after %ss — skipped", label, timeout_s)
        return None
    except Exception as e:
        logger.warning("Optional pass '%s' failed: %s — skipped", label, e)
        return None


# Where to do SEO changes, per platform. Injected into the overview + per-page
# prompts so the "actions" are tool-specific instead of "edit your <head>".
_PLATFORM_HINTS: dict[str, str] = {
    "custom": (
        "Le site est codé sur mesure (HTML/templates maîtrisés). Les actions "
        "peuvent référencer directement le code : balises <head>, templates, "
        "robots.txt, sitemap.xml, headers serveur, build."
    ),
    "webflow": (
        "Le site est sur Webflow. Adapte les actions à Webflow : meta/canonical/"
        "schema via Page Settings → SEO et Custom Code (head/before-body) ; "
        "redirections via Project Settings → Publishing → 301 redirects ; "
        "alt d'image via le Asset panel ; pas d'accès au .htaccess ; sitemap "
        "auto-généré (Project Settings → SEO)."
    ),
    "wordpress": (
        "Le site est sur WordPress. Adapte les actions à WordPress : titles/"
        "meta/canonical/schema via Yoast SEO ou Rank Math ; redirections via "
        "le plugin Redirection ou .htaccess ; alt d'image dans la médiathèque ; "
        "robots.txt/sitemap gérés par le plugin SEO ; perfs via un plugin de "
        "cache (WP Rocket…) + lazy-load natif."
    ),
    "shopify": (
        "Le site est sur Shopify. Adapte les actions : titles/meta via le "
        "champ SEO de chaque produit/collection/page ; canonical et schema "
        "Product gérés par le thème (theme.liquid) ; redirections via "
        "Navigation → URL Redirects ; robots.txt éditable via robots.txt.liquid ; "
        "sitemap auto à /sitemap.xml."
    ),
    "wix": (
        "Le site est sur Wix. Adapte les actions : SEO via le Wix SEO Wiz et "
        "les Settings de chaque page ; balises avancées via Settings → Custom "
        "Code (header/body) ; redirections via Settings → SEO → URL Redirect "
        "Manager ; structured data via les Markup Settings de page."
    ),
    "squarespace": (
        "Le site est sur Squarespace. Adapte les actions : titles/meta via les "
        "Page Settings (SEO tab) et Settings → SEO ; code custom via "
        "Settings → Advanced → Code Injection ; redirections via "
        "Settings → Advanced → URL Mappings ; alt via l'éditeur d'image."
    ),
    "bubble": (
        "Le site est sur Bubble. Adapte les actions : SEO/meta dynamiques via "
        "Settings → SEO/metatags et les champs SEO des pages ; attention au "
        "rendu côté client (SPA) — recommander le plugin de SEO/SSR ou un "
        "prerender ; sitemap via plugin ; pas de .htaccess (redirections via "
        "workflows ou Cloudflare)."
    ),
    "framer": (
        "Le site est sur Framer. Adapte les actions : meta/title/canonical via "
        "les Page Settings (SEO) ; code custom via Site Settings → Custom Code ; "
        "redirections via Site Settings → Redirects ; sitemap auto ; structured "
        "data via Custom Code."
    ),
    "nextjs": (
        "Le site est en Next.js. Adapte les actions : metadata via l'API "
        "metadata (app router) ou next/head ; schema JSON-LD via un <script "
        "type=application/ld+json> dans le layout/page ; redirections via "
        "next.config.js (redirects) ; robots.txt/sitemap via app/robots.ts et "
        "app/sitemap.ts ; vérifier SSR/SSG vs CSR pour les crawlers."
    ),
}


def _platform_block(platform: str) -> str:
    """Returns the platform-specific instruction block, or '' for unknown."""
    hint = _PLATFORM_HINTS.get((platform or "").strip().lower())
    if not hint:
        return ""
    return f"## Plateforme du site\n{hint}\nFormule les `actions` en conséquence.\n"


def analyze(
    crawl: CrawlData,
    *,
    on_progress: Optional[Callable[[str], None]] = None,
    deadline_monotonic: Optional[float] = None,
    platform: str = "unknown",
) -> AuditResult:
    """Run the full multi-pass analysis and return a merged AuditResult.
    `on_progress` receives status strings; `deadline_monotonic` (a time.monotonic
    value) bounds the optional passes so the whole audit can't overrun.
    `platform` adapts the recommendations to the site-builder used."""
    import time as _time
    _p = on_progress or (lambda _m: None)
    pblock = _platform_block(platform)
    if pblock:
        _p(f"Recommandations adaptées à la plateforme : {platform}")

    def _budget(default_s: float) -> float:
        """Remaining time before the deadline, clamped to (5, default_s)."""
        if deadline_monotonic is None:
            return default_s
        remaining = deadline_monotonic - _time.monotonic()
        return max(5.0, min(default_s, remaining))

    crawl_json = _compact_crawl(crawl)

    # Core passes (overview + per-page + missing) are required — wrap each in a
    # generous time box so a single stuck Gemini call can't hang the worker.
    _p("Vue d'ensemble : scoring des 6 axes…")
    overview = _time_boxed(lambda: _run_overview(crawl, crawl_json, pblock), _budget(180), "overview")
    if not isinstance(overview, dict):
        raise ValueError("Overview pass failed or timed out")
    _sanitize_sections(overview)
    time.sleep(INTER_CALL_DELAY_S)

    selected_count = len(_select_pages_for_detail(crawl)[0])
    _p(f"Analyse page par page ({selected_count} pages représentatives)…")
    pages = _time_boxed(
        lambda: _run_pages_batched(crawl, on_progress=_p, platform_block=pblock), _budget(420), "pages"
    ) or []
    pages = _dedupe_pages(pages)
    _sanitize_pages(pages)
    time.sleep(INTER_CALL_DELAY_S)

    _p("Détection des pages manquantes…")
    missing = _time_boxed(lambda: _run_missing(crawl), _budget(120), "missing") or []
    _sanitize_missing(missing)

    # Optional web_search passes — best-effort. We give each a guaranteed small
    # window (≥60s) regardless of how much core-pass budget was eaten by rate
    # limits. Visibility ALWAYS produces something (offline fallback) so the
    # section never disappears.
    time.sleep(INTER_CALL_DELAY_S)
    OPT_MIN_S, OPT_MAX_S = 60.0, 130.0
    _p("Estimation de visibilité organique…")
    if _budget(0.0) > 10:
        vbudget = max(OPT_MIN_S, min(OPT_MAX_S, _budget(OPT_MAX_S)))
        visibility = _time_boxed(lambda: _run_visibility_estimate(crawl, pages), vbudget, "visibility")
    else:
        visibility = None
    if visibility is None:
        # Timed out or deadline reached — still ship the offline estimate.
        _p("Estimation de visibilité : version hors-ligne (délai dépassé)")
        try:
            visibility = _visibility_fallback(crawl, pages)
        except Exception as e:
            logger.warning("Visibility offline fallback failed: %s", e)
            visibility = None
    if _budget(0.0) > 10:
        _p("Analyse SXO (type de page vs SERP)…")
        sbudget = max(OPT_MIN_S, min(OPT_MAX_S, _budget(OPT_MAX_S)))
        sxo = _time_boxed(lambda: _run_sxo(crawl, pages), sbudget, "sxo")
        if sxo is None:
            _p("Analyse SXO ignorée (délai/erreur)")
    else:
        sxo = None
        _p("Analyse SXO ignorée (délai global atteint)")

    _log_coverage(crawl, pages)

    merged: dict = dict(overview)
    merged["pages"] = pages
    merged["missingPages"] = missing
    if visibility is not None:
        merged["visibilityEstimate"] = visibility
    if sxo is not None:
        merged["sxoAudit"] = sxo
    merged.setdefault("id", uuid.uuid4().hex)
    merged.setdefault("createdAt", datetime.now(timezone.utc).isoformat())
    merged.setdefault("domain", crawl.domain)
    merged.setdefault("url", crawl.url)

    # If the model didn't provide a global verdict/score, derive a sane default
    # from the section scores so the audit remains presentable.
    if "scores" in merged and isinstance(merged["scores"], dict):
        scores_vals = [
            v for v in merged["scores"].values() if isinstance(v, (int, float))
        ]
        if "globalScore" not in merged and scores_vals:
            merged["globalScore"] = round(sum(scores_vals) / len(scores_vals))

    merged.setdefault("globalScore", 50)
    merged.setdefault("globalVerdict", "Audit disponible")
    merged.setdefault("sections", [])
    merged.setdefault("quickWins", [])
    merged.setdefault("criticalCount", _count_severity(merged, "critical"))
    merged.setdefault("warningCount", _count_severity(merged, "warning"))

    return AuditResult.model_validate(merged)


def _dedupe_pages(pages: list[dict]) -> list[dict]:
    """Remove duplicate entries (same URL) that a retry might have introduced."""
    seen: set[str] = set()
    result: list[dict] = []
    for p in pages:
        if not isinstance(p, dict):
            continue
        url = p.get("url")
        if not isinstance(url, str) or not url:
            continue
        if url in seen:
            logger.info("Dropping duplicate page entry for %s", url)
            continue
        seen.add(url)
        result.append(p)
    return result


def _count_severity(merged: dict, target: str) -> int:
    """Count findings of a given severity across the overview sections."""
    n = 0
    for section in merged.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for f in section.get("findings") or []:
            if isinstance(f, dict) and f.get("severity") == target:
                n += 1
    return n


# ---------------------------------------------------------------------------
# Stages


def _run_overview(crawl: CrawlData, crawl_json: str, platform_block: str = "") -> dict:
    prompt = _OVERVIEW_TEMPLATE.format(
        domain=crawl.domain,
        url=crawl.url,
        page_count=len(crawl.pages),
        crawl_json=crawl_json,
        performance_block=_format_performance(crawl),
        schemas_block=_format_schemas(crawl),
        link_graph_block=_format_link_graph(crawl),
        quality_block=_format_quality(crawl),
        technical_block=_format_technical(crawl),
        crawl_table_block=_format_technical_crawl(crawl),
    )
    if platform_block:
        prompt = platform_block + "\n" + prompt
    response = get_llm_client().generate(
        system=_SYSTEM, user_prompt=prompt, max_tokens=16000,
        enable_web_search=False,  # the crawl payload is exhaustive; web_search
                                  # here just adds 30-90s with little upside
    )
    return _extract_json(response, tag="OVERVIEW_JSON", context=crawl.domain)


# Mapping returned alongside the selected pages: representative URL ->
# (template pattern, total pages in the group, a few sample URLs).
GroupInfo = dict


def _select_pages_for_detail(crawl: CrawlData) -> tuple[list[CrawlPage], GroupInfo]:
    """Pick pages worth a per-page LLM analysis.

    Strategy:
    1. Detect template groups (≥4 URLs at the same path pattern, e.g. 200
       near-identical blog posts) — analyse ONE representative per group.
    2. From the remaining "unique" pages, prioritise home + hubs + orphans,
       then fill up to MAX_PAGES_DETAILED.

    Returns (selected_pages, group_info) where group_info maps the
    representative's URL to {"pattern", "count", "sampleUrls"}."""
    from urllib.parse import urlparse as _up
    from api.services import programmatic_audit as _pa

    pages = list(crawl.pages)
    by_path = {(_up(p.url).path or "/"): p for p in pages}
    pattern_to_paths = _pa._group_by_pattern(list(by_path.keys()))

    grouped_paths: set[str] = set()
    group_info: GroupInfo = {}
    representatives: list[CrawlPage] = []
    for pattern, member_paths in pattern_to_paths.items():
        members = [by_path[mp] for mp in member_paths if mp in by_path]
        if len(members) < 4:
            continue
        # Representative: prefer one with the most content (likely the richest).
        rep = max(members, key=lambda p: (p.wordCount or 0, len(p.headings or [])))
        representatives.append(rep)
        for m in members:
            grouped_paths.add(_up(m.url).path or "/")
        group_info[rep.url] = {
            "pattern": pattern,
            "count": len(members),
            "sampleUrls": [m.url for m in members[:6]],
        }

    # Unique pages = everything not in a template group.
    uniques = [p for p in pages if (_up(p.url).path or "/") not in grouped_paths]
    hub_urls = set(crawl.linkGraph.hubPages) if crawl.linkGraph else set()
    orphan_urls = set(crawl.linkGraph.orphanPages) if crawl.linkGraph else set()
    priority = [
        p for p in uniques
        if p.url == crawl.url or p.url in hub_urls or p.url in orphan_urls
    ]
    rest = [p for p in uniques if p not in priority]

    # Representatives always make the cut; then priority uniques; then the rest.
    selected = representatives + priority + rest
    selected = selected[:max(MAX_PAGES_DETAILED, len(representatives))]
    # Keep group_info only for representatives that survived the cut.
    sel_urls = {p.url for p in selected}
    group_info = {u: v for u, v in group_info.items() if u in sel_urls}
    return selected, group_info


def _run_pages_batched(
    crawl: CrawlData,
    *,
    on_progress: Optional[Callable[[str], None]] = None,
    platform_block: str = "",
) -> list[dict]:
    """Analyse pages in fixed-size batches so no single response overruns.
    Template groups (e.g. 200 near-identical blog posts) are represented by a
    single page; its analysis is tagged with how many it stands for."""
    _p = on_progress or (lambda _m: None)
    selected, group_info = _select_pages_for_detail(crawl)
    if group_info:
        total_grouped = sum(g["count"] for g in group_info.values())
        _p(
            f"{len(group_info)} groupe(s) de pages au même template détecté(s) — "
            f"1 page type analysée pour {total_grouped} pages"
        )
    batches = _chunk(selected, PAGE_BATCH_SIZE)
    all_pages: list[dict] = []

    for i, batch in enumerate(batches, start=1):
        logger.info(
            "Pages batch %d/%d for %s (%d pages)",
            i, len(batches), crawl.domain, len(batch),
        )
        _p(f"Pages : lot {i}/{len(batches)}…")
        payload = _run_single_pages_batch(crawl.domain, batch, attempt=1, platform_block=platform_block)
        if payload is None:
            _p(f"Pages : lot {i}/{len(batches)} — nouvelle tentative")
            time.sleep(5)
            payload = _run_single_pages_batch(crawl.domain, batch, attempt=2, platform_block=platform_block)

        batch_pages: list = []
        if payload is not None:
            bp = payload.get("pages")
            if isinstance(bp, list):
                batch_pages = bp
            else:
                logger.warning("Batch %d/%d: 'pages' not a list — falling back", i, len(batches))

        # If the whole-batch call failed (or returned junk), try one page at a
        # time so a single bad page doesn't lose the other 9. Any page that
        # still can't be analysed gets a minimal placeholder rather than
        # aborting the entire audit.
        if not batch_pages and len(batch) > 1:
            _p(f"Pages : lot {i}/{len(batches)} — analyse page par page")
            for p in batch:
                single = _run_single_pages_batch(crawl.domain, [p], attempt=1, platform_block=platform_block)
                if single and isinstance(single.get("pages"), list) and single["pages"]:
                    batch_pages.extend(single["pages"])
                else:
                    batch_pages.append(_placeholder_page(p))
                time.sleep(1)
        elif not batch_pages and len(batch) == 1:
            batch_pages = [_placeholder_page(batch[0])]

        all_pages.extend(batch_pages)
        if i < len(batches):
            time.sleep(INTER_CALL_DELAY_S)

    # Tag the representative pages with the size of the template group they
    # stand for, so the report can say "1 page type — vaut pour 198 autres".
    if group_info:
        for pa in all_pages:
            if not isinstance(pa, dict):
                continue
            gi = group_info.get(pa.get("url"))
            if gi:
                pa["representsCount"] = max(0, int(gi.get("count", 0)) - 1)
                pa["representsPattern"] = str(gi.get("pattern", ""))
                pa["representsSampleUrls"] = list(gi.get("sampleUrls", []))[:6]
                # Make it obvious in the page's own findings too.
                msg = (
                    f"Cette page est représentative d'un groupe de {gi.get('count')} "
                    f"pages au même gabarit ({gi.get('pattern')}). Les remarques "
                    "ci-dessous s'appliquent à l'ensemble du groupe."
                )
                fnds = pa.get("findings")
                if isinstance(fnds, list):
                    fnds.insert(0, {
                        "severity": "info",
                        "title": f"Page type — vaut pour {gi.get('count')} pages",
                        "description": msg,
                        "actions": [],
                    })

    return all_pages


def _placeholder_page(p: CrawlPage) -> dict:
    """Minimal PageAnalysis dict for a page the LLM couldn't analyse, so the
    audit ships with a complete page list instead of failing."""
    return {
        "url": p.url,
        "status": "warning",
        "title": p.title or "",
        "titleLength": len(p.title or ""),
        "h1": p.h1 or "",
        "metaDescription": p.metaDescription,
        "metaLength": len(p.metaDescription or "") if p.metaDescription else 0,
        "targetKeywords": [],
        "presentKeywords": [],
        "missingKeywords": [],
        "findings": [
            {
                "severity": "info",
                "title": "Page non analysée en détail",
                "description": (
                    "L'analyse IA détaillée de cette page n'a pas pu aboutir "
                    "(quota/erreur API). Les données techniques du crawl restent "
                    "disponibles ci-dessous."
                ),
                "actions": ["Relancer l'audit pour obtenir l'analyse détaillée de cette page"],
            }
        ],
        "recommendation": None,
    }


def _run_single_pages_batch(
    domain: str,
    batch: list[CrawlPage],
    *,
    attempt: int,
    raise_on_fail: bool = False,
    platform_block: str = "",
) -> Optional[dict]:
    batch_json = json.dumps(
        [
            {
                "url": p.url,
                "title": p.title,
                "h1": p.h1,
                "metaDescription": p.metaDescription,
                "headings": p.headings[:6],
            }
            for p in batch
        ],
        ensure_ascii=False,
        indent=2,
    )
    prompt = _PAGES_BATCH_TEMPLATE.format(
        domain=domain,
        batch_count=len(batch),
        batch_json=batch_json,
    )
    if platform_block:
        prompt = platform_block + "\n" + prompt
    try:
        response = get_llm_client().generate(
            system=_SYSTEM, user_prompt=prompt, max_tokens=16000,
        )
        return _extract_json(
            response, tag="PAGES_JSON", context=f"{domain}/batch",
        )
    except Exception as e:
        logger.warning(
            "Pages batch failed for %s (attempt %d): %s", domain, attempt, e
        )
        if raise_on_fail:
            raise
        return None


def _run_missing(crawl: CrawlData) -> list[dict]:
    existing = "\n".join(f"- {p.url}" for p in crawl.pages)
    prompt = _MISSING_TEMPLATE.format(
        domain=crawl.domain,
        page_count=len(crawl.pages),
        existing_urls=existing,
    )
    try:
        response = get_llm_client().generate(
            system=_SYSTEM, user_prompt=prompt, max_tokens=3500,
        )
        payload = _extract_json(
            response, tag="MISSING_JSON", context=crawl.domain,
        )
    except Exception as e:
        logger.warning("Missing-pages pass failed for %s: %s", crawl.domain, e)
        return []
    result = payload.get("missingPages") or []
    return result if isinstance(result, list) else []


_VISIBILITY_TEMPLATE = """Estimation de visibilité organique pour {domain}.

Tu peux utiliser web_search pour vérifier des ordres de grandeur (volumes de recherche approximatifs, présence de concurrents, SERP réelle sur 2-3 requêtes clés). Tu n'as PAS accès aux bases clickstream (SEMrush/Ahrefs) — tout ce que tu produis est une ESTIMATION assumée.

## Contexte du site (crawl)
- {page_count} pages crawlées
- Thématiques détectées (titres/H1) :
{themes}
- Mots-clés cibles observés sur les pages :
{target_keywords}

## Ce que tu dois produire
1. estimatedMonthlyOrganicTraffic : ordre de grandeur du trafic organique mensuel (entier). Si vraiment impossible, null.
2. trafficRange : fourchette lisible (ex: "300–800 visites/mois").
3. estimatedRankingKeywordsCount : combien de mots-clés ce site rank probablement (ordre de grandeur).
4. topKeywords : 8 à 15 mots-clés sur lesquels le site rank vraisemblablement. Pour chacun : keyword, estimatedMonthlyVolume (ordre de grandeur), estimatedPosition (1-100), rankingUrl (l'URL du site la plus probable), intent ("informational"|"transactional"|"navigational"), note courte.
5. opportunities : 8 à 15 mots-clés que le site DEVRAIT cibler mais ne couvre pas (ou mal). Pour chacun : keyword, estimatedMonthlyVolume, difficulty ("low"|"medium"|"high"), suggestedPage (URL existante à optimiser, ou "(nouvelle page)"), rationale.
6. competitorsLikelyOutranking : 2 à 6 domaines concurrents qui dominent probablement ces SERP.
7. summary : 2-3 phrases de synthèse honnête (forces/faiblesses de visibilité).

## Discipline
- N'invente pas de chiffres précis et faux. Ordres de grandeur uniquement (10, 50, 200, 1000…).
- Si tu n'as aucun signal fiable, mets les champs numériques à null et dis-le dans summary.
- Reste cohérent : un site de 5 pages locales ne fait pas 50 000 visites/mois.

## Sortie STRICTE (aucun texte hors balises)

<VISIBILITY_JSON>
{{
  "estimatedMonthlyOrganicTraffic": 0,
  "trafficRange": "...",
  "estimatedRankingKeywordsCount": 0,
  "topKeywords": [
    {{"keyword": "...", "estimatedMonthlyVolume": 0, "estimatedPosition": 0, "rankingUrl": "...", "intent": "...", "note": "..."}}
  ],
  "opportunities": [
    {{"keyword": "...", "estimatedMonthlyVolume": 0, "difficulty": "low", "suggestedPage": "...", "rationale": "..."}}
  ],
  "competitorsLikelyOutranking": ["..."],
  "summary": "..."
}}
</VISIBILITY_JSON>"""


def _collect_observed_keywords(crawl: CrawlData, pages: list[dict]) -> list[tuple[str, str]]:
    """Keywords observed on the site, paired with the page they were seen on.
    Falls back to titles/H1 of important pages when no targetKeywords."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for p in pages:
        url = p.get("url", "") if isinstance(p, dict) else ""
        for k in (p.get("targetKeywords") or []) if isinstance(p, dict) else []:
            kl = str(k).strip().lower()
            if kl and kl not in seen:
                seen.add(kl)
                out.append((str(k).strip(), url))
    if not out:
        # No target keywords — derive candidates from page titles/H1.
        for cp in crawl.pages[:20]:
            cand = (cp.h1 or cp.title or "").strip()
            cl = cand.lower()
            if cand and cl not in seen and len(cand) <= 80:
                seen.add(cl)
                out.append((cand, cp.url))
    return out[:40]


def _visibility_fallback(crawl: CrawlData, pages: list[dict]) -> dict:
    """A deterministic, no-LLM visibility estimate so the section always
    renders. Numbers are deliberately absent (we can't guess them offline);
    keywords come straight from the crawl."""
    kws = _collect_observed_keywords(crawl, pages)
    n_pages = len(crawl.pages)
    top = [
        {
            "keyword": kw,
            "estimatedMonthlyVolume": None,
            "estimatedPosition": None,
            "rankingUrl": url or crawl.url,
            "intent": "",
            "note": "Observé sur la page (estimation hors-ligne, pas de données SERP)",
        }
        for kw, url in kws[:15]
    ]
    return {
        "disclaimer": (
            "Estimation hors-ligne (la recherche web n'a pas pu être réalisée). "
            "Mots-clés issus du contenu du site ; aucun chiffre de volume/position "
            "fiable disponible — relancez l'audit pour une estimation enrichie."
        ),
        "estimatedMonthlyOrganicTraffic": None,
        "trafficRange": "",
        "estimatedRankingKeywordsCount": None,
        "topKeywords": top,
        "opportunities": [],
        "competitorsLikelyOutranking": [],
        "summary": (
            f"Site de {n_pages} page(s). Thématiques détectées : "
            + ", ".join(kw for kw, _ in kws[:6])
            + ("…" if len(kws) > 6 else "")
            + "." if kws else "Pas de mots-clés clairs détectés dans le contenu."
        ),
    }


def _sanitize_visibility(payload: dict) -> dict:
    def _clamp_int(v, lo=0, hi=10_000_000):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None
        return max(lo, min(hi, n))
    payload["estimatedMonthlyOrganicTraffic"] = _clamp_int(
        payload.get("estimatedMonthlyOrganicTraffic")
    )
    payload["estimatedRankingKeywordsCount"] = _clamp_int(
        payload.get("estimatedRankingKeywordsCount")
    )
    for k in payload.get("topKeywords") or []:
        if isinstance(k, dict):
            k["estimatedMonthlyVolume"] = _clamp_int(k.get("estimatedMonthlyVolume"))
            k["estimatedPosition"] = _clamp_int(k.get("estimatedPosition"), 1, 100)
    for k in payload.get("opportunities") or []:
        if isinstance(k, dict):
            k["estimatedMonthlyVolume"] = _clamp_int(k.get("estimatedMonthlyVolume"))
    return payload


def _run_visibility_estimate(crawl: CrawlData, pages: list[dict]) -> dict:
    """Organic visibility estimate. Tries web_search; on failure retries
    without it; on failure again returns a deterministic offline fallback.
    ALWAYS returns a non-None dict so the section renders."""
    themes = "\n".join(
        f"  - {p.title or p.h1 or p.url}" for p in crawl.pages[:25]
    ) or "  (aucun)"
    kws = _collect_observed_keywords(crawl, pages)
    target_keywords = "\n".join(f"  - {k}" for k, _ in kws) or "  (aucun observé)"
    prompt = _VISIBILITY_TEMPLATE.format(
        domain=crawl.domain,
        page_count=len(crawl.pages),
        themes=themes,
        target_keywords=target_keywords,
    )

    for use_web in (True, False):
        try:
            response = get_llm_client().generate(
                system=_SYSTEM, user_prompt=prompt, max_tokens=6000,
                enable_web_search=use_web,
            )
            payload = _extract_json(response, tag="VISIBILITY_JSON", context=crawl.domain)
            if isinstance(payload, dict) and (payload.get("topKeywords") or payload.get("opportunities")):
                if not use_web:
                    payload.setdefault(
                        "disclaimer",
                        "Estimation IA sans recherche web (la recherche n'a pas abouti) — "
                        "chiffres encore plus indicatifs que d'habitude.",
                    )
                return _sanitize_visibility(payload)
            logger.warning(
                "Visibility pass (web=%s) returned empty payload for %s",
                use_web, crawl.domain,
            )
        except Exception as e:
            logger.warning(
                "Visibility pass (web=%s) failed for %s: %s", use_web, crawl.domain, e
            )

    logger.info("Visibility: using offline fallback for %s", crawl.domain)
    return _visibility_fallback(crawl, pages)


_SXO_TEMPLATE = """Audit SXO (Search Experience Optimization) pour {domain}.

Pour chaque page ci-dessous, on te donne : son URL, son type (notre classification : homepage/article/product/service/localBusiness/faq/contact/about/category/other), son title/H1, et son mot-clé cible principal.

Ta tâche : pour chaque page, utilise web_search sur le mot-clé cible et regarde la SERP Google. Détermine le TYPE de page DOMINANT que Google récompense (ex: 8 fiches produit sur 10 résultats → "product" ; 6 articles de blog → "article" ; 5 pages comparatives → "comparison" ; pages locales → "localBusiness"). Compare avec le type de la page. Si mismatch, c'est une cause majeure de mauvais classement non détectable par un audit technique classique.

Types SERP autorisés : homepage, article, product, service, localBusiness, faq, contact, about, category, comparison, listicle, tool, other.

## Pages à évaluer
{pages_block}

## Pour chaque page, produis
- url
- keyword : le mot-clé évalué
- pageType : le type qu'on t'a donné (recopie-le)
- serpDominantType : le type dominant observé dans la SERP
- match : true si pageType est compatible avec serpDominantType, false sinon
- severity : "ok" si match | "info" si léger écart | "warning" si vrai mismatch | "critical" si la page est totalement le mauvais format
- recommendation : 1 phrase concrète ("Restructurer en page comparative : tableau de X vs Y avec critères et prix" plutôt que "améliorer la page")

## Discipline
- Si tu n'as pas de signal SERP fiable (pas de mot-clé exploitable, requête trop ambiguë), mets severity="ok", match=true, et recommendation="Audit SERP manuel requis".
- N'invente pas un mismatch s'il n'y en a pas.

## Sortie STRICTE (aucun texte hors balises)

<SXO_JSON>
{{
  "verdicts": [
    {{"url": "...", "keyword": "...", "pageType": "...", "serpDominantType": "...", "match": true, "severity": "ok", "recommendation": "..."}}
  ]
}}
</SXO_JSON>"""

_SXO_MAX_PAGES = 8


def _run_sxo(crawl: CrawlData, pages: list[dict]) -> Optional[dict]:
    """Page-type vs SERP-intent mismatch on a sample of important pages.
    LLM + web_search, best-effort. Returns dict matching SxoAuditSummary or None."""
    from api.services import page_classifier

    if not pages and not crawl.pages:
        return None

    # Build candidate list: prefer pages with a target keyword, then hubs,
    # then anything. We need page_type for each — classify on the fly.
    crawl_by_url = {p.url: p for p in (crawl.pages or [])}
    hub_urls = set(crawl.linkGraph.hubPages) if crawl.linkGraph else set()
    home_url = crawl.url

    candidates: list[dict] = []
    for pa in pages:
        cp = crawl_by_url.get(pa.get("url") if isinstance(pa, dict) else getattr(pa, "url", None))
        url = pa["url"] if isinstance(pa, dict) else getattr(pa, "url", "")
        title = pa.get("title", "") if isinstance(pa, dict) else getattr(pa, "title", "")
        h1 = pa.get("h1", "") if isinstance(pa, dict) else getattr(pa, "h1", "")
        kws = pa.get("targetKeywords", []) if isinstance(pa, dict) else getattr(pa, "targetKeywords", [])
        keyword = kws[0] if kws else (title or h1)
        if not keyword:
            continue
        ptype = page_classifier.classify_page(
            url=url, title=title, h1=h1,
            headings=(cp.headings if cp else []),
            text_snippet=(cp.textSnippet if cp else ""),
            schemas=([s.type for s in cp.schemas] if cp and cp.schemas else []),
            word_count=(cp.wordCount if cp else 0),
            is_homepage=(url == home_url),
        )
        priority = 0
        if url in hub_urls:
            priority += 2
        if kws:
            priority += 1
        candidates.append({
            "url": url, "title": title, "h1": h1, "keyword": keyword,
            "pageType": ptype, "_priority": priority,
        })
    if not candidates:
        return None
    candidates.sort(key=lambda c: -c["_priority"])
    sample = candidates[:_SXO_MAX_PAGES]

    pages_block = "\n".join(
        f"- url: {c['url']}\n  type: {c['pageType']}\n  title: {c['title'][:120]}\n  mot-clé cible: {c['keyword']}"
        for c in sample
    )
    prompt = _SXO_TEMPLATE.format(domain=crawl.domain, pages_block=pages_block)
    try:
        response = get_llm_client().generate(
            system=_SYSTEM, user_prompt=prompt, max_tokens=4000,
            enable_web_search=True,
        )
        payload = _extract_json(response, tag="SXO_JSON", context=crawl.domain)
    except Exception as e:
        logger.warning("SXO pass failed for %s: %s", crawl.domain, e)
        return None
    if not isinstance(payload, dict):
        return None
    verdicts = payload.get("verdicts") or []
    if not isinstance(verdicts, list):
        return None
    # Light sanitization.
    valid_sev = {"ok", "info", "warning", "critical"}
    clean: list[dict] = []
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        sev = str(v.get("severity", "ok")).lower()
        if sev not in valid_sev:
            sev = "info"
        v["severity"] = sev
        v["match"] = bool(v.get("match", sev == "ok"))
        clean.append(v)
    mismatches = sum(1 for v in clean if not v.get("match"))
    return {
        "evaluated": len(clean),
        "mismatches": mismatches,
        "verdicts": clean,
    }


_GEO_CITATION_TEMPLATE = """Test de citabilité par les IA pour {domain}.

Tu peux utiliser web_search pour vérifier qui est cité aujourd'hui sur ces requêtes (Google AI Overviews, Perplexity affichent leurs sources ; pour ChatGPT raisonne sur ce qu'il citerait probablement à partir de Wikipedia/Reddit/sites d'autorité).

## Contexte du site
- Thématiques / pages :
{themes}
- Mots-clés observés :
{keywords}

## Ta tâche
Génère {n_queries} requêtes RÉALISTES qu'un utilisateur taperait dans ChatGPT / Perplexity / Google AI à propos de ce domaine d'activité, réparties sur les intentions : informational, transactional, local (si le site est local), navigational. Pour CHAQUE requête, évalue si **ce site précis** serait probablement cité dans la réponse IA, et pourquoi.

## Pour chaque requête, produis
- query : la requête
- intent : "informational" | "transactional" | "local" | "navigational"
- likelyCited : true/false — ce site serait-il cité dans la réponse IA ?
- confidence : "low" | "medium" | "high"
- citingEngines : liste parmi ["Google AI Overviews", "Perplexity", "ChatGPT", "aucun"] — où c'est plausible
- reason : 1 phrase — pourquoi cité (contenu adapté, autorité, schema…) ou pourquoi pas (pas de contenu sur le sujet, contenu mal structuré, site sans autorité…)
- competitorsCitedInstead : 1-4 domaines/marques qui seraient cités à la place
- improvement : 1 action concrète pour devenir citable sur cette requête (ex: "Créer une page FAQ avec une réponse de 130 mots à 'comment X'")

## Discipline
- Sois honnête : un petit site local n'est PAS cité sur des requêtes génériques nationales. Ne mets likelyCited=true que si c'est crédible.
- Si tu ne peux pas vérifier, mets confidence="low".

## Sortie STRICTE (aucun texte hors balises)

<GEO_CITATION_JSON>
{{
  "verdicts": [
    {{"query": "...", "intent": "informational", "likelyCited": false, "confidence": "low", "citingEngines": ["aucun"], "reason": "...", "competitorsCitedInstead": ["..."], "improvement": "..."}}
  ]
}}
</GEO_CITATION_JSON>"""

_GEO_CITATION_QUERIES = 8


def _run_geo_citation(crawl: CrawlData, pages: list[dict]) -> Optional[dict]:
    """LLM + web_search: would AI assistants cite this site on plausible
    intent queries? Returns dict with verdicts/citedCount/queriesTested or
    None on failure."""
    themes = "\n".join(f"  - {p.title or p.h1 or p.url}" for p in crawl.pages[:20]) or "  (aucun)"
    kws = [k for k, _ in _collect_observed_keywords(crawl, pages)][:25]
    keywords = "\n".join(f"  - {k}" for k in kws) or "  (aucun)"
    prompt = _GEO_CITATION_TEMPLATE.format(
        domain=crawl.domain, themes=themes, keywords=keywords,
        n_queries=_GEO_CITATION_QUERIES,
    )
    try:
        response = get_llm_client().generate(
            system=_SYSTEM, user_prompt=prompt, max_tokens=5000, enable_web_search=True,
        )
        payload = _extract_json(response, tag="GEO_CITATION_JSON", context=crawl.domain)
    except Exception as e:
        logger.warning("GEO citation pass failed for %s: %s", crawl.domain, e)
        return None
    if not isinstance(payload, dict):
        return None
    verdicts = payload.get("verdicts")
    if not isinstance(verdicts, list):
        return None
    clean: list[dict] = []
    valid_intent = {"informational", "transactional", "local", "navigational"}
    valid_conf = {"low", "medium", "high"}
    for v in verdicts:
        if not isinstance(v, dict) or not v.get("query"):
            continue
        intent = str(v.get("intent", "")).lower()
        v["intent"] = intent if intent in valid_intent else "informational"
        conf = str(v.get("confidence", "low")).lower()
        v["confidence"] = conf if conf in valid_conf else "low"
        v["likelyCited"] = bool(v.get("likelyCited"))
        if not isinstance(v.get("citingEngines"), list):
            v["citingEngines"] = []
        if not isinstance(v.get("competitorsCitedInstead"), list):
            v["competitorsCitedInstead"] = []
        clean.append(v)
    cited = sum(1 for v in clean if v.get("likelyCited"))
    return {
        "queryVerdicts": clean,
        "citedCount": cited,
        "queriesTested": len(clean),
    }


# ---------------------------------------------------------------------------
# Helpers


# Above this many crawled pages, the full per-page block in the overview
# prompt becomes too large / costly. We keep ALL pages in the link-graph and
# the technical/quality aggregates, but truncate the per-page detail list
# down to a representative sample (hubs first, then the rest) and tell the
# model the total so it knows it's looking at a sample.
_OVERVIEW_PAGE_DETAIL_CAP = 60


def _compact_crawl(crawl: CrawlData) -> str:
    pages = list(crawl.pages)
    total = len(pages)
    sampled = False
    if total > _OVERVIEW_PAGE_DETAIL_CAP:
        sampled = True
        hub_urls = set(crawl.linkGraph.hubPages) if crawl.linkGraph else set()
        orphan_urls = set(crawl.linkGraph.orphanPages) if crawl.linkGraph else set()
        # Priority: home + hubs + orphans (they carry the actionable findings),
        # then fill with the rest in crawl order.
        priority = [p for p in pages if p.url in hub_urls or p.url in orphan_urls or p.url == crawl.url]
        rest = [p for p in pages if p not in priority]
        pages = (priority + rest)[:_OVERVIEW_PAGE_DETAIL_CAP]

    compact = [
        {
            "url": p.url,
            "title": p.title,
            "h1": p.h1,
            "metaDescription": p.metaDescription,
            "headings": p.headings[:6],
            "wordCount": p.wordCount,
            "canonical": p.canonical,
            "robotsMeta": p.robotsMeta or None,
            "schemas": [
                {"type": s.type, "format": s.format, "status": s.status}
                for s in p.schemas
            ],
        }
        for p in pages
    ]
    payload: dict = {"domain": crawl.domain, "url": crawl.url, "pages": compact}
    if sampled:
        payload["_note"] = (
            f"{total} pages crawlées au total ; détail par page limité à "
            f"{len(compact)} (hubs + orphelines + échantillon). Les agrégats "
            "maillage / technique / qualité plus bas couvrent les "
            f"{total} pages."
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _format_schemas(crawl: CrawlData) -> str:
    """Factual summary of detected Schema.org markup across the site."""
    total: dict[tuple[str, str], int] = {}
    issues: list[str] = []
    for page in crawl.pages:
        for s in page.schemas:
            key = (s.type, s.status)
            total[key] = total.get(key, 0) + 1
            for issue in s.issues:
                msg = f"[{s.type}] {issue}"
                if msg not in issues:
                    issues.append(msg)

    if not total:
        return (
            "## Schema.org détecté (analyse Python, factuelle)\n"
            "Aucune donnée structurée détectée sur le site (ni JSON-LD, ni Microdata, ni RDFa). "
            "→ Recommander l'ajout de types pertinents (Organization/WebSite a minima, "
            "LocalBusiness si local, Product/Article selon cas)."
        )

    lines = ["## Schema.org détecté (analyse Python, factuelle)"]
    for (schema_type, status), count in sorted(total.items()):
        badge = {
            "active": "✓ actif",
            "restricted": "⚠ restreint",
            "deprecated": "✗ déprécié",
            "unknown": "? inconnu",
        }.get(status, status)
        lines.append(f"- **{schema_type}** — {badge} — {count} page(s)")
    if issues:
        lines.append("### Problèmes détectés")
        for i in issues[:10]:
            lines.append(f"- {i}")
    lines.append(
        "→ Utilise ces données comme source de vérité pour les findings "
        "schema dans l'axe `seo` (ne pas deviner, ne pas recommander ce qui est déjà présent)."
    )
    return "\n".join(lines)


def _format_technical_crawl(crawl: CrawlData) -> str:
    """Screaming-Frog-style crawl aggregates for the analyzer prompt."""
    tc = crawl.technicalCrawl
    if tc is None or tc.pagesCrawled == 0:
        return (
            "## Crawl technique (analyse Python, façon Screaming Frog)\n"
            "Pas de données de crawl technique."
        )
    lines = [
        "## Crawl technique (analyse Python, façon Screaming Frog)",
        f"Pages/URLs visitées : {tc.pagesCrawled} · "
        f"indexables : {tc.indexablePages} · non-indexables : {tc.nonIndexablePages} · "
        f"profondeur max : {tc.maxDepth} clics",
        f"Codes HTTP : {', '.join(f'{k}×{v}' for k, v in sorted(tc.statusCounts.items()))}",
    ]

    def _grp(name: str, groups: list[list[str]]) -> None:
        if not groups:
            return
        lines.append(f"### {name} ({len(groups)} groupe(s))")
        for g in groups[:6]:
            lines.append(f"- {len(g)} pages : {', '.join(g[:4])}{' …' if len(g) > 4 else ''}")

    def _lst(name: str, urls: list[str]) -> None:
        if not urls:
            return
        lines.append(f"### {name} ({len(urls)})")
        for u in urls[:8]:
            lines.append(f"- {u}")
        if len(urls) > 8:
            lines.append(f"- … (+{len(urls) - 8})")

    _grp("Titres dupliqués", tc.duplicateTitles)
    _grp("Meta descriptions dupliquées", tc.duplicateMetaDescriptions)
    _grp("H1 dupliqués", tc.duplicateH1s)
    _lst("Pages sans <title>", tc.missingTitles)
    _lst("Pages sans meta description", tc.missingMetaDescriptions)
    _lst("Pages sans H1", tc.missingH1)
    _lst("Titres trop longs (> 60 car.)", tc.titleTooLong)
    _lst("Titres trop courts (< 30 car.)", tc.titleTooShort)
    _lst("Meta trop longues (> 160 car.)", tc.metaTooLong)
    _lst("Meta trop courtes (< 70 car.)", tc.metaTooShort)
    _lst("Pages à faible ratio texte/HTML (< 10%)", tc.lowTextRatioPages)
    _lst("Liens internes cassés (cibles 4xx/5xx)", tc.brokenInternalLinks)

    # Per-page issue digest (top 15 most-issued pages)
    issued = sorted(
        [r for r in tc.rows if r.issues], key=lambda r: -len(r.issues)
    )[:15]
    if issued:
        lines.append("### Pages avec le plus de problèmes (digest)")
        for r in issued:
            lines.append(
                f"- {r.url} [{r.statusCode}, profondeur {r.depth}] : {'; '.join(r.issues)}"
            )

    lines.append(
        "→ Tous ces points sont OBSERVÉS. Crée des findings concrets dans "
        "`seo` (titres/meta/H1/canonical/redirections), `performance` "
        "(ratio texte/HTML, taille HTML), `ux` (viewport, mixed content). "
        "Donne pour chaque finding la liste des URLs concernées et l'action "
        "exacte. Ne pas re-deviner."
    )
    return "\n".join(lines)


def _format_technical(crawl: CrawlData) -> str:
    """Canonicals, robots meta, hreflang coverage, image hygiene."""
    lines = ["## Technical SEO on-page (analyse Python, factuelle)"]

    # Canonicals
    no_canon = [p for p in crawl.pages if not p.canonical]
    bad_canon = [
        p for p in crawl.pages
        if p.canonical and p.canonical not in (p.url, p.finalUrl)
    ]
    lines.append(f"### Canonicals — {len(crawl.pages) - len(no_canon)}/{len(crawl.pages)} pages avec <link rel=\"canonical\">")
    if no_canon:
        lines.append(f"Pages SANS canonical ({len(no_canon)}) :")
        for p in no_canon[:8]:
            lines.append(f"- {p.url}")
    if bad_canon:
        lines.append(f"Pages avec canonical pointant AILLEURS (potentiel duplicate ou erreur) :")
        for p in bad_canon[:8]:
            lines.append(f"- {p.url} → canonical={p.canonical}")

    # Robots meta
    noindex = [p for p in crawl.pages if "noindex" in p.robotsMeta]
    if noindex:
        lines.append(f"### Pages noindex ({len(noindex)}) — vérifier que c'est intentionnel")
        for p in noindex[:8]:
            lines.append(f"- {p.url} (robots={p.robotsMeta})")

    # Hreflang
    pages_with_hreflang = [p for p in crawl.pages if p.hreflang]
    if pages_with_hreflang:
        lines.append(
            f"### Hreflang détecté sur {len(pages_with_hreflang)}/{len(crawl.pages)} pages"
        )
        sample = pages_with_hreflang[0]
        langs = ", ".join(sorted({h.lang for h in sample.hreflang}))
        lines.append(f"Langues déclarées (échantillon {sample.url}) : {langs}")
        # Validation: x-default present, self-reference present, two-way?
        all_langs = sorted({h.lang for p in pages_with_hreflang for h in p.hreflang})
        if "x-default" not in all_langs:
            lines.append("⚠ Pas de `x-default` détecté — recommandé par Google.")
    elif crawl.pages and any(p.htmlLang and "-" in p.htmlLang for p in crawl.pages):
        lines.append("### Hreflang absent — pas de tag `alternate hreflang` détecté")
        lines.append("Le site utilise des langs régionalisés mais ne déclare pas hreflang : risque de contenu dupliqué inter-pays.")

    # html lang
    html_langs = sorted({p.htmlLang for p in crawl.pages if p.htmlLang})
    if html_langs:
        lines.append(f"### `<html lang>` observés : {', '.join(html_langs)}")

    # Images
    total_imgs = sum(len(p.images) for p in crawl.pages)
    no_alt = sum(p.imagesWithoutAlt for p in crawl.pages)
    if total_imgs:
        modern = sum(
            1 for p in crawl.pages for i in p.images
            if i.fileFormat in ("webp", "avif")
        )
        legacy = sum(
            1 for p in crawl.pages for i in p.images
            if i.fileFormat in ("jpg", "jpeg", "png")
        )
        no_dim = sum(
            1 for p in crawl.pages for i in p.images
            if not i.isInlineSvg and (i.width is None or i.height is None)
        )
        no_lazy = sum(
            1 for p in crawl.pages for i in p.images
            if not i.isInlineSvg and i.loading != "lazy"
        )
        lines.append(
            f"### Images — {total_imgs} balises <img> sur {len(crawl.pages)} pages"
        )
        lines.append(
            f"- Sans attribut `alt` (CRITIQUE accessibilité + SEO) : {no_alt}"
        )
        lines.append(
            f"- Formats modernes (webp/avif) : {modern} · legacy (jpg/png) : {legacy}"
        )
        lines.append(
            f"- Sans width/height (CLS risk) : {no_dim}"
        )
        lines.append(
            f"- Sans `loading=\"lazy\"` (perf) : {no_lazy}"
        )

    if len(lines) == 1:
        lines.append("Aucun signal technique on-page anormal détecté.")
    lines.append(
        "→ Findings issus de ces données vont dans `seo` (canonicals, hreflang, "
        "robots) et `performance`/`content` (images sans alt → ux+content, "
        "formats legacy + no lazy → performance). Cite les URLs/comptes vus ci-dessus."
    )
    return "\n".join(lines)


def _format_quality(crawl: CrawlData) -> str:
    """Duplicates, redirect chains, thin pages — factual block."""
    lines = ["## Qualité technique on-page (analyse Python, factuelle)"]

    # Thin content
    thin = [p for p in crawl.pages if 0 < p.wordCount < 300]
    if thin:
        lines.append(f"### Pages thin content (< 300 mots) — {len(thin)}")
        for p in thin[:10]:
            lines.append(f"- {p.url} ({p.wordCount} mots)")

    # Duplicates
    if crawl.duplicates:
        exact = [d for d in crawl.duplicates if d.kind == "exact"]
        near = [d for d in crawl.duplicates if d.kind == "near"]
        lines.append(
            f"### Duplicate content — {len(exact)} exact, {len(near)} near"
        )
        for d in (exact + near)[:10]:
            lines.append(
                f"- [{d.kind}] {d.urlA} ↔ {d.urlB} (similarity {d.similarity})"
            )

    # Redirect chains
    if crawl.redirectChains:
        long_chains = [c for c in crawl.redirectChains if c.hopCount >= 1]
        if long_chains:
            lines.append(
                f"### Redirections — {len(long_chains)} URL(s) atteignent "
                "leur cible via une redirection"
            )
            for c in long_chains[:8]:
                lines.append(
                    f"- {c.requestUrl} → {c.finalUrl} ({c.hopCount} hop(s))"
                )

    if len(lines) == 1:
        lines.append(
            "Aucun signal qualité on-page détecté (pas de thin content < 300 mots, "
            "pas de duplicates, pas de chaînes de redirection)."
        )
    lines.append(
        "→ Findings issus de ces données vont dans la section `seo` ou `content` "
        "(thin → content, duplicates/redirects → seo). Ne pas inventer."
    )
    return "\n".join(lines)


def _format_link_graph(crawl: CrawlData) -> str:
    """Compact rendering of the internal link graph for the analyzer prompt."""
    graph = crawl.linkGraph
    if graph is None or graph.totalEdges == 0:
        return (
            "## Maillage interne (analyse Python, factuelle)\n"
            "Aucun lien interne extrait — pages probablement isolées ou rendu JS bloquant."
        )
    lines = [
        "## Maillage interne (analyse Python, factuelle)",
        f"Total liens internes (toutes pages confondues) : {graph.totalEdges}",
    ]
    if graph.hubPages:
        lines.append("### Hubs (top in-degree, pages les plus liées)")
        for url in graph.hubPages:
            stat = next((p for p in graph.pages if p.url == url), None)
            indeg = stat.inDegree if stat else 0
            lines.append(f"- {url} (in-degree {indeg})")
    if graph.orphanPages:
        lines.append(
            f"### Pages orphelines ({len(graph.orphanPages)}) — aucun lien interne entrant détecté"
        )
        for url in graph.orphanPages[:10]:
            lines.append(f"- {url}")
        if len(graph.orphanPages) > 10:
            lines.append(f"- … (+{len(graph.orphanPages) - 10} autres)")
    if graph.topAnchorTexts:
        lines.append("### Anchor texts les plus utilisés")
        lines.append(", ".join(f'"{a}"' for a in graph.topAnchorTexts[:10]))
    if graph.deadLinks:
        lines.append(f"### Liens internes cassés ({len(graph.deadLinks)})")
        for dl in graph.deadLinks[:10]:
            status = dl.statusCode if dl.statusCode is not None else "no response"
            lines.append(
                f"- {dl.target} → {status} (lié depuis {dl.sourceCount} page(s))"
            )
    lines.append(
        "→ Utilise ces données pour : findings d'orphan pages, sur-utilisation "
        "d'anchors génériques (\"cliquez ici\"), liens cassés, distribution "
        "déséquilibrée du jus interne. Ne pas inventer, citer les URLs vues ci-dessus."
    )
    return "\n".join(lines)


def _format_performance(crawl: CrawlData) -> str:
    """Human-readable block describing Core Web Vitals for the analyzer prompt.

    When no PSI data is available we tell the model to mark performance as an
    estimation. When CrUX/Lighthouse returned values, we list them with ratings
    so the LLM bases its score on facts, not guesses.
    """
    perf = crawl.performance
    if perf is None or perf.source == "unavailable":
        reason = (perf.error if perf else None) or "clé PageSpeed Insights non configurée"
        return (
            "## Core Web Vitals — PAS DE DONNÉES TERRAIN\n"
            f"Raison : {reason}\n"
            "→ Note la section `performance` comme *estimation* (source=estimated). "
            "Indique dans le verdict de l'axe : « estimation, données CrUX indisponibles »."
        )
    lines: list[str] = [
        f"## Core Web Vitals — source : {perf.source} ({perf.strategy})"
    ]
    if perf.performanceScore is not None:
        lines.append(f"Lighthouse performance score : **{perf.performanceScore}/100**")
    if not perf.metrics:
        lines.append("Aucune métrique retournée par l'API.")
    for m in perf.metrics:
        parts = [f"**{m.name}**"]
        if m.fieldValue is not None:
            parts.append(f"field p75={m.fieldValue}{_unit_for(m.name)}")
        if m.labValue is not None:
            parts.append(f"lab={m.labValue}{_unit_for(m.name)}")
        if m.rating:
            parts.append(f"rating={m.rating}")
        if m.threshold:
            parts.append(f"seuil={m.threshold}")
        lines.append(" · ".join(parts))
    extras = list(getattr(crawl, "performanceExtra", []) or [])
    if extras:
        lines.append("### Mesures additionnelles (pages hub)")
        for snap in extras:
            if snap.source == "unavailable":
                continue
            score_part = (
                f" — score {snap.performanceScore}/100"
                if snap.performanceScore is not None
                else ""
            )
            lines.append(f"- {snap.url} (source={snap.source}{score_part})")
            for m in snap.metrics:
                parts = [f"  · **{m.name}**"]
                if m.fieldValue is not None:
                    parts.append(f"field p75={m.fieldValue}{_unit_for(m.name)}")
                if m.labValue is not None:
                    parts.append(f"lab={m.labValue}{_unit_for(m.name)}")
                if m.rating:
                    parts.append(f"rating={m.rating}")
                lines.append(" · ".join(parts))
    lines.append(
        "→ Base le score de l'axe `performance` sur ces VALEURS RÉELLES. "
        "Rappelle dans le verdict que ce sont des mesures (CrUX/Lighthouse), "
        "pas une estimation."
    )
    return "\n".join(lines)


def _unit_for(metric: str) -> str:
    if metric == "CLS":
        return ""
    return "ms"


def _chunk(items: list, size: int) -> list[list]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


# ---------------------------------------------------------------------------
# Enum sanitization
#
# The model occasionally mixes adjacent enums (e.g. emits `improve` in a
# finding severity, which is only valid for page status; or `high` in
# `effort` which is only valid for `impact`). We correct these at the
# boundary rather than fail the whole audit, and log every correction so
# drift can be monitored.

_SEVERITY_ALIASES = {
    "improve": "warning",
    "improvement": "warning",
    "attention": "warning",
    "ok": "ok",
    "pass": "ok",
    "good": "ok",
    "critical": "critical",
    "warning": "warning",
    "info": "info",
    "missing": "missing",
}

_PAGE_STATUS_ALIASES = {
    "critical": "critical",
    "warning": "warning",
    "improve": "improve",
    "ok": "ok",
    "info": "improve",
    "missing": "critical",
}

_IMPACT_ALIASES = {"high": "high", "medium": "medium", "low": "low"}

_EFFORT_ALIASES = {
    "quick": "quick",
    "medium": "medium",
    "heavy": "heavy",
    # Model sometimes emits impact-values into effort
    "high": "heavy",
    "low": "quick",
}

_PRIORITY_ALIASES = {"high": "high", "medium": "medium", "low": "low"}


def _sanitize_enum(
    raw,
    aliases: dict[str, str],
    *,
    field: str,
    context: str,
    fallback: Optional[str] = None,
) -> Optional[str]:
    if raw is None:
        return fallback
    if not isinstance(raw, str):
        logger.warning(
            "Sanitizing non-string value for %s in %s: %r", field, context, raw
        )
        return fallback
    key = raw.strip().lower()
    if key in aliases:
        normalized = aliases[key]
        if normalized != raw:
            logger.info(
                "Sanitized %s in %s: %r -> %r", field, context, raw, normalized
            )
        return normalized
    logger.warning(
        "Unknown %s value in %s: %r (falling back to %r)",
        field, context, raw, fallback,
    )
    return fallback


# Phrases that signal a finding is vague filler with nothing actionable
# behind it. If a non-"ok" finding has only this kind of language and no
# concrete actions, we downgrade it to `info` so it doesn't masquerade as
# a real recommendation in the report.
_VAGUE_MARKERS = (
    "peut être amélioré",
    "peuvent être améliorés",
    "des optimisations sont possibles",
    "des améliorations sont possibles",
    "n'est pas optimal",
    "n'est pas optimale",
    "pourrait être optimisé",
    "à améliorer",
    "à optimiser",
    "revoir la structure",
    "améliorer le contenu",
    "travailler le seo",
    "optimiser les images",
)


def _is_actionable(actions: object) -> bool:
    """An actions list counts as actionable if it has ≥1 item that is not
    itself a vague restatement (must reference something concrete: a slash,
    a tag, a quote, a digit, or a CMS/file keyword)."""
    if not isinstance(actions, list):
        return False
    concrete_signals = ("/", "<", '"', "«", "http", ":")
    for a in actions:
        if not isinstance(a, str):
            continue
        s = a.strip()
        if len(s) < 15:
            continue
        low = s.lower()
        if any(m in low for m in _VAGUE_MARKERS):
            continue
        if any(sig in s for sig in concrete_signals) or any(ch.isdigit() for ch in s):
            return True
    return False


def _sanitize_finding(f: dict, *, context: str) -> Optional[dict]:
    severity = _sanitize_enum(
        f.get("severity"), _SEVERITY_ALIASES,
        field="finding.severity", context=context, fallback=None,
    )
    if severity is None:
        logger.warning("Dropping finding without valid severity in %s", context)
        return None
    f["severity"] = severity
    if "impact" in f and f["impact"] is not None:
        f["impact"] = _sanitize_enum(
            f["impact"], _IMPACT_ALIASES,
            field="finding.impact", context=context, fallback=None,
        )
    if "effort" in f and f["effort"] is not None:
        f["effort"] = _sanitize_enum(
            f["effort"], _EFFORT_ALIASES,
            field="finding.effort", context=context, fallback=None,
        )

    # Vagueness guard: a critical/warning finding with no concrete actions and
    # filler-only description is downgraded to info. We keep it (the signal
    # might be real) but it stops being presented as an actionable fix.
    if severity in ("critical", "warning"):
        desc = (f.get("description") or "").lower()
        title = (f.get("title") or "").lower()
        actionable = _is_actionable(f.get("actions"))
        looks_vague = any(m in desc for m in _VAGUE_MARKERS) or (
            len(desc) < 40 and not any(ch.isdigit() for ch in desc) and "/" not in desc
        )
        if not actionable and looks_vague:
            logger.warning(
                "Downgrading vague %s finding '%s' to info in %s (no concrete actions)",
                severity, title[:60], context,
            )
            f["severity"] = "info"
    return f


def _as_list(v: object) -> list:
    return v if isinstance(v, list) else []


_VALID_SECTIONS = frozenset(
    ("security", "seo", "ux", "content", "performance", "business")
)

# Aliases: sometimes the model invents a 7th section or uses a near-synonym.
# We fold those findings into an existing axis rather than dropping them.
_SECTION_ALIASES = {
    "images": "content",
    "image": "content",
    "media": "content",
    "schema": "seo",
    "structured_data": "seo",
    "ai_search": "business",
    "geo": "business",
    "ai": "business",
    "on_page": "seo",
    "on-page": "seo",
    "onpage": "seo",
    "technical": "seo",
    "local": "business",
}


def _sanitize_sections(overview: dict) -> None:
    sections = _as_list(overview.get("sections"))
    # 1. Normalize every section's `section` field and merge invalid ones into
    #    the canonical axis if an alias exists, otherwise drop the section.
    normalized: dict[str, dict] = {}
    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        raw = str(section.get("section", "")).strip().lower()
        canonical = raw if raw in _VALID_SECTIONS else _SECTION_ALIASES.get(raw)
        if canonical is None:
            logger.warning(
                "Dropping unknown section %r (no alias) at index %d",
                raw, i,
            )
            continue
        if canonical != raw:
            logger.info("Folding section %r into %r", raw, canonical)
        sec_name = section.get("section") or f"section[{i}]"
        cleaned_findings: list[dict] = []
        for f in _as_list(section.get("findings")):
            if not isinstance(f, dict):
                continue
            s = _sanitize_finding(f, context=f"overview/{sec_name}")
            if s is not None:
                cleaned_findings.append(s)
        section["section"] = canonical
        section["findings"] = cleaned_findings
        # Merge duplicates (e.g. images → content twice): concatenate findings.
        if canonical in normalized:
            normalized[canonical]["findings"].extend(cleaned_findings)
        else:
            normalized[canonical] = section

    overview["sections"] = list(normalized.values())


def _sanitize_pages(pages: list[dict]) -> None:
    for p in pages:
        if not isinstance(p, dict):
            continue
        url = p.get("url") or "?"
        status = _sanitize_enum(
            p.get("status"), _PAGE_STATUS_ALIASES,
            field="page.status", context=url, fallback="warning",
        )
        p["status"] = status
        cleaned: list[dict] = []
        for f in _as_list(p.get("findings")):
            if not isinstance(f, dict):
                continue
            s = _sanitize_finding(f, context=f"page:{url}")
            if s is not None:
                cleaned.append(s)
        p["findings"] = cleaned


def _sanitize_missing(pages: list[dict]) -> None:
    for m in pages:
        if not isinstance(m, dict):
            continue
        m["priority"] = _sanitize_enum(
            m.get("priority"), _PRIORITY_ALIASES,
            field="missingPage.priority",
            context=m.get("url") or "?",
            fallback="medium",
        )


def _log_coverage(crawl: CrawlData, pages: list[dict]) -> None:
    covered = {p.get("url") for p in pages if isinstance(p, dict) and p.get("url")}
    missing = [p.url for p in crawl.pages if p.url not in covered]
    if missing:
        logger.warning(
            "Analyzer coverage gap on %s: %d/%d pages analysed (first missing: %s)",
            crawl.domain,
            len(covered),
            len(crawl.pages),
            missing[:3],
        )


# ---------------------------------------------------------------------------
# JSON extraction (balanced-brace, tolerant to a missing closing tag)


def _extract_json(response: LLMResponse, *, tag: str, context: str) -> dict:
    text = response.text
    open_re = re.compile(f"<{tag}>", re.IGNORECASE)
    m = open_re.search(text)
    start = text.find("{", m.end()) if m else text.find("{")
    if start < 0:
        _raise("no-opening-brace", response, context, tag)

    candidate = _scan_balanced_object(text, start)
    if candidate is None:
        _raise("truncated", response, context, tag)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        logger.error(
            "JSONDecodeError on %s/%s at char %d: %s",
            context, tag, e.pos, e.msg,
        )
        snippet = candidate[-300:]
        raise ValueError(
            f"JSON invalide retourné par l'analyse ({tag}): {e.msg} "
            f"(extrait: {snippet!r})"
        ) from e


def _scan_balanced_object(text: str, start: int) -> Optional[str]:
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


def _raise(kind: str, response: LLMResponse, context: str, tag: str) -> None:
    text = response.text
    snippet = text.strip()[-300:]
    logger.error(
        "%s extraction failed (%s, stop=%s/%s, out_tokens=%s, len=%d) for %s",
        tag, kind, response.stop_reason, response.raw_stop_reason,
        response.output_tokens, len(text), context,
    )
    if kind == "truncated":
        raise ValueError(
            f"Réponse tronquée pour {tag} (max_tokens atteint). Fin: {snippet!r}"
        )
    raise ValueError(f"Aucun JSON exploitable pour {tag}. Fin: {snippet!r}")


# ---------------------------------------------------------------------------
# Competitor Watch — compare several completed audits into one LLM synthesis.


_COMPETITOR_SYSTEM = (
    "Tu es un consultant senior spécialisé en analyse concurrentielle web. "
    "À partir de plusieurs audits déjà produits sur le même secteur, tu "
    "identifies qui gagne sur chaque axe, les forces et faiblesses du site "
    "cible par rapport aux concurrents, et les actions prioritaires à "
    "engager. Tu es factuel, concis, pas de hype.\n"
    "RÈGLES DE SORTIE : 1. QUE le bloc <COMPETITOR_JSON> sans texte autour. "
    "2. Terminer TOUJOURS par </COMPETITOR_JSON>. "
    "3. 1-2 phrases max par item (≤ 220 chars)."
)


_COMPETITOR_TEMPLATE = """Analyse concurrentielle : {target_url} vs {n_competitors} concurrents.

Site cible : {target_url}
Concurrents : {competitor_urls}

Résumé des audits (scores + findings clés par axe) :
{audits_summary}

QUOTAS DE SORTIE :
- winnersByAxis : un gagnant par axe sur 6 (security/seo/ux/content/performance/business). Valeur = URL du gagnant (target ou concurrent).
- keyInsights : 3 à 5 observations factuelles sur le positionnement.
- ourStrengths : 2 à 4 forces du site cible vs concurrents.
- ourWeaknesses : 2 à 4 faiblesses mesurables.
- priorityActions : 3 à 6 actions prioritaires pour rattraper/creuser l'écart, par impact décroissant.
- verdict : 1-2 phrases résumant la position concurrentielle globale.

Sortie STRICTE (aucun texte hors balises) :

<COMPETITOR_JSON>
{{
  "winnersByAxis": {{
    "security": "https://example.com",
    "seo": "https://example.com",
    "ux": "https://example.com",
    "content": "https://example.com",
    "performance": "https://example.com",
    "business": "https://example.com"
  }},
  "keyInsights": ["...", "..."],
  "ourStrengths": ["...", "..."],
  "ourWeaknesses": ["...", "..."],
  "priorityActions": ["...", "..."],
  "verdict": "..."
}}
</COMPETITOR_JSON>
"""


def compare_competitors(
    target: AuditResult,
    competitors: list[AuditResult],
) -> CompetitorReport:
    """Produce a comparative report between `target` and `competitors`.

    Never raises on LLM failure — returns a minimal fallback report based on
    raw score comparisons so the UI always has something to display.
    """
    if not competitors:
        return _fallback_report(target, competitors)

    summary_lines: list[str] = []
    for label, audit in [("CIBLE", target)] + [
        (f"C{i + 1}", c) for i, c in enumerate(competitors)
    ]:
        summary_lines.append(_summarize_audit_for_compare(label, audit))
    audits_summary = "\n\n".join(summary_lines)

    competitor_urls = ", ".join(c.url for c in competitors)
    prompt = _COMPETITOR_TEMPLATE.format(
        target_url=target.url,
        n_competitors=len(competitors),
        competitor_urls=competitor_urls,
        audits_summary=audits_summary,
    )

    try:
        response = get_llm_client().generate(
            system=_COMPETITOR_SYSTEM,
            user_prompt=prompt,
            max_tokens=4500,
            enable_web_search=False,
        )
        payload = _extract_json(
            response, tag="COMPETITOR_JSON", context=target.domain,
        )
    except Exception as e:
        logger.warning("Competitor LLM call failed for %s: %s", target.domain, e)
        return _fallback_report(target, competitors)

    try:
        return CompetitorReport.model_validate(payload)
    except Exception as e:
        logger.warning("Competitor payload invalid for %s: %s", target.domain, e)
        return _fallback_report(target, competitors)


def _summarize_audit_for_compare(label: str, audit: AuditResult) -> str:
    scores = audit.scores or {}
    scores_str = " · ".join(
        f"{axis}={scores.get(axis, 0)}"
        for axis in ("security", "seo", "ux", "content", "performance", "business")
    )
    top_findings: list[str] = []
    for section in (audit.sections or [])[:6]:
        critical = [f.title for f in section.findings if f.severity == "critical"]
        if critical:
            top_findings.append(
                f"[{section.section}] {critical[0][:80]}"
            )
    findings_str = (
        "\n    Top findings critiques : "
        + "; ".join(top_findings[:4])
        if top_findings
        else ""
    )
    return (
        f"{label} — {audit.url}\n"
        f"  Score global : {audit.globalScore}/100 ({audit.globalVerdict or ''})\n"
        f"  Scores : {scores_str}"
        f"{findings_str}"
    )


def _fallback_report(
    target: AuditResult, competitors: list[AuditResult],
) -> CompetitorReport:
    """Minimal report computed from raw scores when the LLM is unavailable."""
    all_audits = [target] + competitors
    winners: dict[str, str] = {}
    for axis in ("security", "seo", "ux", "content", "performance", "business"):
        best = max(all_audits, key=lambda a: a.scores.get(axis, 0))  # type: ignore[arg-type]
        winners[axis] = best.url

    target_scores = target.scores or {}
    strengths: list[str] = []
    weaknesses: list[str] = []
    for axis, score in target_scores.items():
        others = [c.scores.get(axis, 0) for c in competitors]
        if not others:
            continue
        avg = sum(others) / len(others)
        delta = score - avg
        label = {
            "security": "Sécurité",
            "seo": "SEO",
            "ux": "UX",
            "content": "Contenu",
            "performance": "Performance",
            "business": "Business",
        }.get(axis, axis)
        if delta >= 10:
            strengths.append(
                f"{label} : +{int(delta)} pts vs moyenne concurrents"
            )
        elif delta <= -10:
            weaknesses.append(
                f"{label} : {int(delta)} pts vs moyenne concurrents"
            )

    return CompetitorReport(
        winnersByAxis=winners,
        keyInsights=[
            f"Comparaison basique entre {target.domain} et "
            f"{len(competitors)} concurrents (synthèse LLM indisponible).",
        ],
        ourStrengths=strengths[:4] or ["Aucune force majeure identifiée sans LLM."],
        ourWeaknesses=weaknesses[:4] or ["Aucune faiblesse majeure identifiée sans LLM."],
        priorityActions=[
            "Relancer la comparaison pour générer la synthèse LLM complète.",
        ],
        verdict=None,
    )
