"""GEO (Generative Engine Optimization) — AI-citability scoring.

LLM-powered search (ChatGPT browsing, Perplexity, Claude, Google AI
Overviews) cites pages that are *citable*: self-contained passages of
~134-167 words that answer a question directly, question-style headings,
attributed stats, server-rendered HTML, an llms.txt manifest, and AI
crawlers allowed in robots.txt. This module scores each crawled page on
those signals (0-100) and a site-level layer for robots/llms.txt.

Methodology adapted from AgriciDaniel/claude-seo (skills/seo-geo).
Pure Python — works from the crawl data we already have.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# AI crawler user-agents to look for in robots.txt.
AI_CRAWLERS = {
    "GPTBot": "OpenAI (ChatGPT training)",
    "OAI-SearchBot": "OpenAI (ChatGPT search)",
    "ChatGPT-User": "OpenAI (ChatGPT browsing)",
    "ClaudeBot": "Anthropic (Claude training)",
    "anthropic-ai": "Anthropic",
    "Claude-Web": "Anthropic (Claude browsing)",
    "PerplexityBot": "Perplexity",
    "Perplexity-User": "Perplexity (browsing)",
    "Google-Extended": "Google (Gemini training — n'affecte PAS Google Search)",
    "CCBot": "Common Crawl",
    "Bytespider": "ByteDance",
    "cohere-ai": "Cohere",
}

_QUESTION_WORDS = (
    "comment", "pourquoi", "qu'est-ce", "quel", "quelle", "quels", "quelles",
    "quand", "où", "combien", "qui", "est-ce", "what", "why", "how", "when",
    "where", "who", "which", "is ", "are ", "can ", "should ", "does ",
)

# Cheap "looks like a number/stat" detector for attribution checks.
_STAT_RE = re.compile(r"\b\d{1,3}(?:[ ,.]\d{3})*(?:[.,]\d+)?\s?(%|€|\$|millions?|milliards?|million|billion|k\b|x\b)", re.I)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# SPA shell hint (same idea as playwright_fetcher).
_SPA_HINTS = (
    '<div id="root"', "<div id='root'", '<div id="app"', "<div id='app'",
    '<div id="__next"', 'data-reactroot', 'ng-version=', 'data-v-app',
)


def _is_question(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if t.endswith("?"):
        return True
    return t.startswith(_QUESTION_WORDS)


def score_page(
    *,
    word_count: int,
    headings: list[str],
    text_snippet: str,
    schemas: list[str],
    rendered_with_playwright: bool,
    has_author_signal: bool = False,
) -> tuple[int, list[str], list[str]]:
    """Return (score 0-100, list of strengths, list of weaknesses)."""
    headings = headings or []
    strengths: list[str] = []
    weaknesses: list[str] = []
    score = 0.0

    # 1. Question-style headings (25 pts) — match conversational queries.
    q_headings = [h for h in headings if _is_question(h)]
    if headings:
        ratio = len(q_headings) / len(headings)
        pts = round(min(ratio * 2, 1.0) * 25)  # 50%+ of headings as questions = full marks
        score += pts
        if ratio >= 0.3:
            strengths.append(f"{len(q_headings)}/{len(headings)} headings sous forme de question")
        else:
            weaknesses.append("Peu de headings sous forme de question (les LLM matchent les requêtes conversationnelles)")
    else:
        weaknesses.append("Aucun heading structurant détecté")

    # 2. Passage length (20 pts) — content long enough to host a citable
    #    passage but structured. We approximate from word_count + heading count.
    if word_count <= 0:
        weaknesses.append("Contenu textuel quasi nul (page peu citable)")
    elif word_count < 200:
        score += 5
        weaknesses.append("Contenu très court (< 200 mots) — difficile à citer")
    elif word_count <= 2500 and len(headings) >= 3:
        score += 20
        strengths.append(f"Contenu structuré ({word_count} mots, {len(headings)} sections)")
    elif word_count > 2500 and len(headings) < 4:
        score += 8
        weaknesses.append("Contenu long mais peu segmenté — un LLM ne trouve pas de passage autonome")
    else:
        score += 15

    # 3. Stats / attribution (15 pts).
    has_stat = bool(_STAT_RE.search(text_snippet or "")) or any(_STAT_RE.search(h) for h in headings)
    has_year = bool(_YEAR_RE.search(text_snippet or ""))
    if has_stat:
        score += 12
        strengths.append("Statistiques chiffrées présentes (favorisent la citation)")
        if has_year:
            score += 3
    else:
        weaknesses.append("Pas de statistique/chiffre attribuable détecté")

    # 4. Technical accessibility — SSR vs CSR (20 pts).
    if rendered_with_playwright:
        score += 4
        weaknesses.append("Contenu rendu côté client (JS) — les crawlers AI voient peu/pas le contenu")
    else:
        score += 20
        strengths.append("Contenu présent dans le HTML initial (lisible par les crawlers AI)")

    # 5. Structured data (20 pts) — schema helps entity resolution.
    schemas_low = {s.lower() for s in (schemas or [])}
    useful = schemas_low & {
        "article", "blogposting", "newsarticle", "faqpage", "howto",
        "product", "organization", "person", "localbusiness", "qapage",
    }
    if useful:
        score += 20
        strengths.append(f"Schema.org présent : {', '.join(sorted(useful))}")
    else:
        weaknesses.append("Aucun schema.org utile — l'IA résout moins bien l'entité")

    # Bonus: author signal (we rarely have this; +0 if absent).
    if has_author_signal:
        strengths.append("Auteur identifié (signal E-E-A-T pour la citation)")

    return max(0, min(100, round(score))), strengths, weaknesses


def score_site_layer(
    *,
    robots_txt: str | None,
    has_llms_txt: bool,
) -> tuple[list[str], list[str], dict[str, str]]:
    """Site-level GEO signals. Returns (strengths, weaknesses, ai_crawler_status)
    where ai_crawler_status maps each known AI UA -> "allowed" | "blocked" |
    "not mentioned"."""
    strengths: list[str] = []
    weaknesses: list[str] = []
    status: dict[str, str] = {}

    txt = robots_txt or ""
    # Very small robots.txt parser focused on AI UAs.
    lines = [l.strip() for l in txt.splitlines()]
    blocks: list[tuple[list[str], list[str]]] = []  # (user-agents, disallow paths)
    cur_ua: list[str] = []
    cur_dis: list[str] = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        if low.startswith("user-agent:"):
            if cur_ua and (cur_dis or True):
                blocks.append((cur_ua, cur_dis))
            ua_val = line.split(":", 1)[1].strip()
            # consecutive User-agent lines group
            if cur_ua and not cur_dis:
                cur_ua.append(ua_val)
            else:
                cur_ua = [ua_val]
                cur_dis = []
        elif low.startswith("disallow:"):
            cur_dis.append(line.split(":", 1)[1].strip())
        elif low.startswith("allow:"):
            pass
    if cur_ua:
        blocks.append((cur_ua, cur_dis))

    def _blocked(ua: str) -> str:
        ua_l = ua.lower()
        for uas, dis in blocks:
            for u in uas:
                if u.lower() == ua_l or u == "*":
                    # blocked if any Disallow: / (root)
                    if any(d == "/" for d in dis):
                        return "blocked" if u.lower() == ua_l else "blocked (via *)"
                    if u.lower() == ua_l:
                        return "allowed"
        return "not mentioned"

    for ua in AI_CRAWLERS:
        status[ua] = _blocked(ua)

    # Headline assessments.
    important = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "PerplexityBot"]
    blocked_important = [u for u in important if status.get(u, "").startswith("blocked")]
    if blocked_important:
        weaknesses.append(
            "Crawlers AI bloqués dans robots.txt : " + ", ".join(blocked_important)
            + " — ces moteurs ne pourront pas citer le site."
        )
    else:
        strengths.append("Aucun crawler AI majeur bloqué dans robots.txt")

    if has_llms_txt:
        strengths.append("/llms.txt présent (manifeste pour les LLM)")
    else:
        weaknesses.append("/llms.txt absent — recommandé pour guider les LLM vers le contenu clé")

    return strengths, weaknesses, status
