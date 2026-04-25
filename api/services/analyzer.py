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
from datetime import datetime, timezone
from typing import Optional

from api.models import AuditResult, CompetitorReport, CrawlData, CrawlPage
from api.services.llm import LLMResponse, get_llm_client

logger = logging.getLogger(__name__)

PAGE_BATCH_SIZE = 6  # pages per PAGES call — keeps responses ~5-7K tokens
INTER_CALL_DELAY_S = 2.5


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
- description : 1 à 2 phrases (≤ 220 chars)
- recommendation : 1 à 2 phrases (≤ 220 chars)
- actions : 2 à 5 items ≤ 140 chars chacun. Chaque action = étape technique concrète (ex: "Ajouter <meta name=\\"description\\"> sur /faq via Webflow → Page Settings → SEO").
- verdict d'axe : 1 phrase courte (style "Bon niveau, quelques améliorations ciblées" ou "À consolider — headers sécurité absents, RGPD partiel").
- quickWins : 4 à 8 items priorisés par ratio impact/effort.

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


def analyze(crawl: CrawlData) -> AuditResult:
    """Run the full multi-pass analysis and return a merged AuditResult."""
    crawl_json = _compact_crawl(crawl)

    overview = _run_overview(crawl, crawl_json)
    if not isinstance(overview, dict):
        raise ValueError("Overview response is not a JSON object")
    _sanitize_sections(overview)
    time.sleep(INTER_CALL_DELAY_S)

    pages = _run_pages_batched(crawl)
    pages = _dedupe_pages(pages)
    _sanitize_pages(pages)
    time.sleep(INTER_CALL_DELAY_S)

    missing = _run_missing(crawl)
    _sanitize_missing(missing)

    _log_coverage(crawl, pages)

    merged: dict = dict(overview)
    merged["pages"] = pages
    merged["missingPages"] = missing
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


def _run_overview(crawl: CrawlData, crawl_json: str) -> dict:
    prompt = _OVERVIEW_TEMPLATE.format(
        domain=crawl.domain,
        url=crawl.url,
        page_count=len(crawl.pages),
        crawl_json=crawl_json,
        performance_block=_format_performance(crawl),
        schemas_block=_format_schemas(crawl),
    )
    response = get_llm_client().generate(
        system=_SYSTEM, user_prompt=prompt, max_tokens=16000,
    )
    return _extract_json(response, tag="OVERVIEW_JSON", context=crawl.domain)


def _run_pages_batched(crawl: CrawlData) -> list[dict]:
    """Analyse pages in fixed-size batches so no single response overruns."""
    batches = _chunk(crawl.pages, PAGE_BATCH_SIZE)
    all_pages: list[dict] = []

    for i, batch in enumerate(batches, start=1):
        logger.info(
            "Pages batch %d/%d for %s (%d pages)",
            i, len(batches), crawl.domain, len(batch),
        )
        payload = _run_single_pages_batch(crawl.domain, batch, attempt=1)
        if payload is None:
            time.sleep(5)
            payload = _run_single_pages_batch(
                crawl.domain, batch, attempt=2, raise_on_fail=True,
            )
        assert payload is not None
        batch_pages = payload.get("pages") or []
        if not isinstance(batch_pages, list):
            raise ValueError(
                f"Batch {i}/{len(batches)} returned 'pages' that is not a list"
            )
        all_pages.extend(batch_pages)
        if i < len(batches):
            time.sleep(INTER_CALL_DELAY_S)

    return all_pages


def _run_single_pages_batch(
    domain: str,
    batch: list[CrawlPage],
    *,
    attempt: int,
    raise_on_fail: bool = False,
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


# ---------------------------------------------------------------------------
# Helpers


def _compact_crawl(crawl: CrawlData) -> str:
    compact = [
        {
            "url": p.url,
            "title": p.title,
            "h1": p.h1,
            "metaDescription": p.metaDescription,
            "headings": p.headings[:6],
            "schemas": [
                {"type": s.type, "format": s.format, "status": s.status}
                for s in p.schemas
            ],
        }
        for p in crawl.pages
    ]
    return json.dumps(
        {"domain": crawl.domain, "url": crawl.url, "pages": compact},
        ensure_ascii=False,
        indent=2,
    )


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
