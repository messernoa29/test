"""AI Search Visibility — does the target site get cited by AI engines?

For each input query, we ask the LLM (with grounding/web_search enabled) the
question and observe:
- Whether `targetDomain` appears in the citations metadata.
- Whether the answer text mentions the brand explicitly.
- The list of competing sources cited.

Once every query is probed, an LLM synthesis call summarizes the visibility
and proposes actions.

Stays vendor-agnostic by going through `api.services.llm.get_llm_client()`.
The Gemini provider exposes `grounding_metadata` natively when grounding is
enabled; we extract URIs out of the response when present, otherwise fall
back to text-search heuristics on the answer body.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from api.models import (
    AiCitation,
    AiQueryResult,
    AiVisibilityCheck,
    AiVisibilityReport,
)
from api.services.llm import LLMResponse, get_llm_client

logger = logging.getLogger(__name__)


_PROBE_SYSTEM = (
    "Tu es un assistant de recherche. Tu réponds factuellement à la question "
    "posée en t'appuyant sur des sources web vérifiables. Tu cites tes "
    "sources sous la forme [n] avec une liste finale numérotée des URLs. "
    "Si tu ne trouves rien de pertinent, tu le dis."
)

_PROBE_TEMPLATE = """Réponds à la question suivante de manière utile et factuelle, en citant tes sources web.

Question : {query}

Format de réponse imposé :
1. Une réponse synthétique en 4 à 8 phrases.
2. Puis une section "Sources :" avec une liste numérotée des URLs réellement utilisées (pas plus de 8).

Pas de blabla introductif, va droit au but."""


_REPORT_SYSTEM = (
    "Tu es un consultant senior en visibilité AI / GEO (Generative Engine "
    "Optimization). Tu analyses les retours d'un moteur AI sur plusieurs "
    "requêtes pour conclure si un site est cité ou non, ses points forts et "
    "ses actions prioritaires. Tu écris en français concis. "
    "RÈGLES DE SORTIE : 1. QUE le bloc <AI_VIS_JSON> sans texte autour. "
    "2. Toujours terminer par </AI_VIS_JSON>. "
    "3. 1-2 phrases max par item (≤ 220 chars)."
)

_REPORT_TEMPLATE = """Analyse les retours suivants d'un moteur AI sur plusieurs requêtes ciblant le site {target}.
Cite explicitement les axes d'amélioration GEO (Generative Engine Optimization) à exploiter.

QUOTAS :
- summary : 2-3 phrases qui résument la position AI du site.
- citationRate : déjà calculé côté serveur, à recopier tel quel.
- mentionRate : idem.
- strengths : 2-4 forces (ex : déjà cité sur tel sujet, signal d'autorité).
- weaknesses : 2-4 faiblesses (ex : aucune citation sur tel topic, concurrent dominant).
- actions : 4-6 actions GEO concrètes (llms.txt, structured data, FAQ schema, brand mentions).

DONNÉES BRUTES (probes) :
{probes_json}

DONNÉES CALCULÉES :
- citationRate = {citation_rate}
- mentionRate = {mention_rate}

Sortie STRICTE :

<AI_VIS_JSON>
{{
  "summary": "...",
  "citationRate": {citation_rate},
  "mentionRate": {mention_rate},
  "strengths": ["..."],
  "weaknesses": ["..."],
  "actions": ["..."]
}}
</AI_VIS_JSON>
"""


def create_check(
    target_domain: str, queries: list[str], target_name: Optional[str] = None,
) -> AiVisibilityCheck:
    return AiVisibilityCheck(
        id=uuid.uuid4().hex,
        targetDomain=_normalize_domain(target_domain),
        targetName=(target_name or "").strip() or None,
        queries=[q.strip() for q in queries if q.strip()][:10],
        createdAt=datetime.now(timezone.utc).isoformat(),
        status="pending",
    )


def run_check_pipeline(check: AiVisibilityCheck) -> AiVisibilityCheck:
    """Probe every query then ask the LLM to summarise."""
    probes: list[AiQueryResult] = []
    for query in check.queries:
        probe = _probe_query(check.targetDomain, check.targetName, query)
        probes.append(probe)

    citation_rate = _rate(probes, lambda p: p.cited)
    mention_rate = _rate(probes, lambda p: p.targetMentioned)

    report = _synthesize(
        target=check.targetName or check.targetDomain,
        probes=probes,
        citation_rate=citation_rate,
        mention_rate=mention_rate,
    )
    return check.model_copy(
        update={"probes": probes, "report": report, "status": "done"},
    )


# ---------------------------------------------------------------------------
# Probe one query


_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>,;]+", re.IGNORECASE)


def _probe_query(target_domain: str, target_name: Optional[str], query: str) -> AiQueryResult:
    client = get_llm_client()
    try:
        response = client.generate(
            system=_PROBE_SYSTEM,
            user_prompt=_PROBE_TEMPLATE.format(query=query),
            max_tokens=2000,
            enable_web_search=True,
        )
    except Exception as e:
        logger.warning("AI probe failed for %r: %s", query, e)
        return AiQueryResult(
            engine=client.name,
            query=query,
            error=str(e)[:200],
        )

    answer = response.text or ""
    citations = _extract_citations(answer)
    cited = any(_url_matches(c.url or "", target_domain) for c in citations)
    mentioned = _text_mentions(answer, target_name, target_domain)

    return AiQueryResult(
        engine=client.name,
        query=query,
        answer=answer,
        cited=cited,
        targetMentioned=mentioned,
        citations=citations,
    )


def _extract_citations(text: str) -> list[AiCitation]:
    """Pull URLs from the answer body. Robust to numbered "Sources :" lists."""
    seen: set[str] = set()
    citations: list[AiCitation] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:)")
        if url in seen:
            continue
        seen.add(url)
        citations.append(AiCitation(url=url))
    return citations[:12]


def _url_matches(url: str, target_domain: str) -> bool:
    if not url or not target_domain:
        return False
    return _normalize_domain(target_domain) in url.lower()


def _text_mentions(
    text: str, target_name: Optional[str], target_domain: str,
) -> bool:
    if not text:
        return False
    t = text.lower()
    if target_name and len(target_name) >= 3 and target_name.lower() in t:
        return True
    domain_root = _normalize_domain(target_domain).split(".")[0]
    if len(domain_root) >= 4 and domain_root.lower() in t:
        return True
    return False


def _normalize_domain(d: str) -> str:
    d = d.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0]
    d = d.removeprefix("www.")
    return d


# ---------------------------------------------------------------------------
# Synthesize report


def _rate(probes: list[AiQueryResult], pred) -> float:
    if not probes:
        return 0.0
    valid = [p for p in probes if p.error is None]
    if not valid:
        return 0.0
    return round(sum(1 for p in valid if pred(p)) / len(valid), 3)


def _synthesize(
    target: str,
    probes: list[AiQueryResult],
    citation_rate: float,
    mention_rate: float,
) -> AiVisibilityReport:
    if not probes:
        return AiVisibilityReport(
            summary="Aucune requête sondée.",
            citationRate=0.0,
            mentionRate=0.0,
        )

    probes_compact = [
        {
            "query": p.query,
            "cited": p.cited,
            "mentioned": p.targetMentioned,
            "answer": (p.answer or "")[:600],
            "citations": [c.url for c in p.citations[:6]],
            "error": p.error,
        }
        for p in probes
    ]

    prompt = _REPORT_TEMPLATE.format(
        target=target,
        probes_json=json.dumps(probes_compact, ensure_ascii=False, indent=2),
        citation_rate=citation_rate,
        mention_rate=mention_rate,
    )

    try:
        response = get_llm_client().generate(
            system=_REPORT_SYSTEM,
            user_prompt=prompt,
            max_tokens=4000,
            enable_web_search=False,
        )
    except Exception as e:
        logger.warning("AI visibility synthesis failed: %s", e)
        return _fallback_report(citation_rate, mention_rate)

    payload = _extract_tagged_json(response, tag="AI_VIS_JSON")
    if payload is None:
        return _fallback_report(citation_rate, mention_rate)
    # Force the rates to the server-computed values (the LLM sometimes drifts).
    payload["citationRate"] = citation_rate
    payload["mentionRate"] = mention_rate
    try:
        return AiVisibilityReport.model_validate(payload)
    except Exception as e:
        logger.warning("AI visibility report invalid: %s", e)
        return _fallback_report(citation_rate, mention_rate)


def _fallback_report(citation_rate: float, mention_rate: float) -> AiVisibilityReport:
    return AiVisibilityReport(
        summary=(
            "Synthèse LLM indisponible — voir les retours requête par requête. "
            f"Taux de citation : {round(citation_rate * 100)}%. "
            f"Taux de mention : {round(mention_rate * 100)}%."
        ),
        citationRate=citation_rate,
        mentionRate=mention_rate,
        strengths=["Utiliser les requêtes où le site est déjà cité comme socle."],
        weaknesses=["Renforcer la présence sur les requêtes où aucune citation n'apparaît."],
        actions=[
            "Publier un fichier llms.txt à la racine.",
            "Ajouter Schema.org Organization + Article structurés.",
            "Créer des passages 134-167 mots avec réponses directes.",
            "Renforcer l'autorité (Wikipedia, Reddit, presse).",
        ],
    )


def _extract_tagged_json(response: LLMResponse, *, tag: str) -> Optional[dict]:
    text = response.text
    if not text:
        return None
    open_re = re.compile(f"<{tag}>", re.IGNORECASE)
    m = open_re.search(text)
    start = text.find("{", m.end()) if m else text.find("{")
    if start < 0:
        return None
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
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None
