"""Content Brief — produce an editorial brief from a target search query.

Pipeline :
1. Ask the LLM (Gemini 3 Pro with `google_search` grounding, or Anthropic +
   web_search) to enumerate the top organic results for the query and pull
   their structural signals (title, H1, headings, meta).
2. Feed that SERP digest back to the LLM with strict JSON instructions to
   produce a complete editorial brief: outline, intent, audience, FAQ, etc.

The first call doubles as the SERP-scraper because re-implementing the search
ourselves would require SerpAPI / Bing API budget. Letting the grounded LLM
do it keeps the dependency stack lean and respects the same per-LLM rate
limits as the rest of the app.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from api.models import (
    ContentBrief,
    ContentBriefOutline,
    ContentBriefResult,
    SerpResult,
)
from api.services.llm import LLMResponse, get_llm_client

logger = logging.getLogger(__name__)


_SERP_SYSTEM = (
    "Tu es un analyste SEO qui inspecte les SERP. Tu utilises l'outil de "
    "recherche web pour collecter les 8 à 10 premiers résultats organiques "
    "réels d'une requête. Tu retournes UNIQUEMENT un JSON balisé, sans "
    "aucun texte autour, et toujours fermé par la balise </SERP_JSON>."
)

_SERP_TEMPLATE = """Recherche la requête suivante dans Google ({locale}) et retourne les **8 à 10 premiers résultats organiques** réels.

Requête : "{query}"

Pour chaque résultat, capture :
- rank : 1, 2, 3, … (ordre d'apparition)
- url : URL absolue du résultat
- title : balise <title> exacte de la page
- h1 : H1 visible (vide si introuvable)
- headings : 3 à 8 H2/H3 principaux dans l'ordre
- metaDescription : meta description visible (null si absente)
- wordCount : estimation du nombre de mots de l'article (null si non estimable)

NE PRODUIS AUCUNE ANALYSE. Que les données factuelles.

Sortie STRICTE :

<SERP_JSON>
{{
  "results": [
    {{
      "rank": 1,
      "url": "...",
      "title": "...",
      "h1": "...",
      "headings": ["..."],
      "metaDescription": "..." ou null,
      "wordCount": 0 ou null
    }}
  ]
}}
</SERP_JSON>
"""


_BRIEF_SYSTEM = (
    "Tu es un consultant éditorial SEO senior, à jour sur les guidelines "
    "Google 2025-2026 (E-E-A-T, AI Overviews, Helpful Content fusionné dans "
    "le core algo). Tu produis des briefs prêts à transmettre à un rédacteur. "
    "Tu écris en français concis, factuel, sans hype. "
    "RÈGLES DE SORTIE : 1. QUE le bloc <BRIEF_JSON> sans aucun texte autour. "
    "2. Toujours terminer par </BRIEF_JSON>. "
    "3. Phrases courtes (≤ 220 chars) par item."
)

_BRIEF_TEMPLATE = """À partir de l'analyse SERP ci-dessous, produis un brief éditorial complet pour la requête : "{query}".

QUOTAS :
- summary : 2-3 phrases sur la nature du sujet et l'angle recommandé.
- intent : "informational" | "commercial" | "navigational" | "transactional".
- targetAudience : 1 phrase décrivant le persona principal.
- suggestedTitle : title balise (≤ 60 chars), inclut le mot-clé principal.
- suggestedMeta : meta description (140-160 chars), incite au clic.
- h1 : différent du title, plus naturel.
- targetWordCount : entier, basé sur la moyenne SERP (généralement 1200-2500).
- primaryKeywords : 3-5 mots-clés principaux à viser.
- semanticKeywords : 8-15 mots-clés sémantiques connexes.
- outline : 6 à 10 H2 dans l'ordre, chacun avec :
    - title (≤ 80 chars)
    - intent (1 phrase courte sur ce que la section couvre)
    - bullets : 2-5 H3 ou points clés
    - targetWords : portion approximative des mots à allouer
- faq : 4-6 questions reformulées que les internautes posent (utile pour AI Overviews).
- quickWins : 3-6 conseils pour battre les concurrents (citabilité AI, schémas, sources).
- notes : 1 phrase finale (concurrence, difficulté, opportunité).

DONNÉES SERP :
{serp_json}

Sortie STRICTE :

<BRIEF_JSON>
{{
  "summary": "...",
  "intent": "informational",
  "targetAudience": "...",
  "suggestedTitle": "...",
  "suggestedMeta": "...",
  "h1": "...",
  "targetWordCount": 0,
  "primaryKeywords": ["..."],
  "semanticKeywords": ["..."],
  "outline": [
    {{
      "title": "...",
      "intent": "...",
      "bullets": ["..."],
      "targetWords": 0
    }}
  ],
  "faq": ["..."],
  "quickWins": ["..."],
  "notes": "..."
}}
</BRIEF_JSON>
"""


_TAG_RE_CACHE: dict[str, re.Pattern] = {}


def _open_re(tag: str) -> re.Pattern:
    if tag not in _TAG_RE_CACHE:
        _TAG_RE_CACHE[tag] = re.compile(f"<{tag}>", re.IGNORECASE)
    return _TAG_RE_CACHE[tag]


def run_brief_pipeline(brief: ContentBrief) -> ContentBrief:
    """Mutate the brief through the SERP → analysis → result phases."""
    serp_results = _fetch_serp(brief.query, brief.locale)
    brief = brief.model_copy(update={"serpResults": serp_results})

    if not serp_results:
        logger.warning(
            "Brief %s: SERP scrape returned no result, generating brief without context",
            brief.id,
        )

    result = _generate_brief(brief.query, serp_results)
    brief = brief.model_copy(update={"result": result, "status": "done"})
    return brief


def create_brief(query: str, locale: str = "fr-FR") -> ContentBrief:
    return ContentBrief(
        id=uuid.uuid4().hex,
        query=query.strip(),
        locale=locale,
        createdAt=datetime.now(timezone.utc).isoformat(),
        status="pending",
    )


# ---------------------------------------------------------------------------
# Internals


def _fetch_serp(query: str, locale: str) -> list[SerpResult]:
    prompt = _SERP_TEMPLATE.format(query=query, locale=locale)
    try:
        response = get_llm_client().generate(
            system=_SERP_SYSTEM,
            user_prompt=prompt,
            max_tokens=6000,
            enable_web_search=True,
        )
    except Exception as e:
        logger.warning("SERP probe failed: %s", e)
        return []

    payload = _extract_tagged_json(response, tag="SERP_JSON")
    if not payload:
        return []
    raw = payload.get("results") or []
    if not isinstance(raw, list):
        return []

    results: list[SerpResult] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        try:
            results.append(SerpResult.model_validate(r))
        except Exception as e:
            logger.debug("Skipping malformed SERP entry: %s", e)
    return results[:10]


def _generate_brief(
    query: str, serp_results: list[SerpResult],
) -> ContentBriefResult:
    serp_compact = [
        {
            "rank": r.rank,
            "url": r.url,
            "title": r.title,
            "h1": r.h1,
            "headings": r.headings[:8],
            "metaDescription": r.metaDescription,
            "wordCount": r.wordCount,
        }
        for r in serp_results
    ]
    serp_json = json.dumps(
        {"query": query, "results": serp_compact}, ensure_ascii=False, indent=2,
    )
    prompt = _BRIEF_TEMPLATE.format(query=query, serp_json=serp_json)
    response = get_llm_client().generate(
        system=_BRIEF_SYSTEM,
        user_prompt=prompt,
        max_tokens=8000,
        enable_web_search=False,
    )
    payload = _extract_tagged_json(response, tag="BRIEF_JSON")
    if payload is None:
        raise ValueError("La synthèse de brief n'a pas produit de JSON exploitable.")
    # Sanitize outline entries that come as strings (rare LLM glitch)
    outline_raw = payload.get("outline") or []
    outline: list[ContentBriefOutline] = []
    for item in outline_raw:
        if isinstance(item, str):
            outline.append(ContentBriefOutline(title=item))
            continue
        if not isinstance(item, dict):
            continue
        try:
            outline.append(ContentBriefOutline.model_validate(item))
        except Exception:
            continue
    payload["outline"] = [o.model_dump() for o in outline]
    return ContentBriefResult.model_validate(payload)


def _extract_tagged_json(response: LLMResponse, *, tag: str) -> Optional[dict]:
    text = response.text
    if not text:
        return None
    m = _open_re(tag).search(text)
    start = text.find("{", m.end()) if m else text.find("{")
    if start < 0:
        logger.warning(
            "%s extraction: no opening brace (stop=%s)", tag, response.stop_reason,
        )
        return None
    candidate = _scan_balanced_object(text, start)
    if candidate is None:
        logger.warning("%s extraction: truncated", tag)
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        logger.warning("%s JSON invalid: %s", tag, e)
        return None


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
