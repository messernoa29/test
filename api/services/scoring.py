"""Deterministic per-axis scores derived from the crawl facts.

The point: two audits of the same unchanged site must give (almost) the
same scores. A pure-LLM score oscillates a few points run to run. So we
compute a base score per axis from the hard facts we already collected
(status codes, duplicate titles/meta, text ratio, canonicals, images
without alt, Core Web Vitals, accessibility signals, internal-link graph,
schema, robots/llms.txt…). The LLM then gets these base scores and may
adjust each by ±10 with a written reason — its judgement still matters,
but the floor/ceiling is factual and stable.

All six axes: security, seo, ux, content, performance, business.
"""

from __future__ import annotations


def _clamp(n: float) -> int:
    return max(0, min(100, round(n)))


def _ratio(numer: int, denom: int) -> float:
    return (numer / denom) if denom else 0.0


def compute_axis_scores(crawl) -> dict[str, int]:
    """Return {axis: base_score} computed from crawl facts only."""
    pages = list(crawl.pages or [])
    n_pages = len(pages) or 1
    tc = crawl.technicalCrawl
    perf = crawl.performance

    # --- shared aggregates -------------------------------------------------
    imgs_total = sum(len(p.images) for p in pages)
    imgs_no_alt = sum(p.imagesWithoutAlt for p in pages)
    pages_no_canonical = sum(1 for p in pages if not p.canonical)
    pages_noindex = sum(1 for p in pages if "noindex" in (p.robotsMeta or ""))
    pages_no_title = sum(1 for p in pages if not p.title)
    pages_no_meta = sum(1 for p in pages if not p.metaDescription)
    pages_no_h1 = sum(1 for p in pages if not p.h1)
    title_too_long = sum(1 for p in pages if p.title and len(p.title) > 60)
    thin_pages = sum(1 for p in pages if 0 < p.wordCount < 300)
    mixed_content = sum(1 for p in pages if getattr(p, "hasMixedContent", False))
    https = crawl.url.lower().startswith("https://")
    redirect_chains = len([c for c in (crawl.redirectChains or []) if c.hopCount >= 2])
    duplicates = len(crawl.duplicates or [])

    # technical-crawl extras
    status_4xx = status_5xx = 0
    broken_links = 0
    if tc:
        for code, n in (tc.statusCounts or {}).items():
            try:
                c = int(code)
                if 400 <= c < 500:
                    status_4xx += n
                elif 500 <= c < 600:
                    status_5xx += n
            except ValueError:
                pass
        broken_links = len(tc.brokenInternalLinks or [])
        dup_titles = len(tc.duplicateTitles or [])
        dup_meta = len(tc.duplicateMetaDescriptions or [])
    else:
        dup_titles = dup_meta = 0

    # link graph
    orphans = len(crawl.linkGraph.orphanPages) if crawl.linkGraph else 0
    dead_links = len(crawl.linkGraph.deadLinks) if crawl.linkGraph else 0

    # schema
    has_schema = any(p.schemas for p in pages)

    # a11y aggregates (if present)
    a11y_pages = [p for p in pages if p.a11y is not None]
    a11y_no_lang = sum(1 for p in a11y_pages if not p.a11y.htmlHasLang)
    a11y_no_label = sum(p.a11y.formInputsWithoutLabel for p in a11y_pages)
    a11y_div_buttons = sum(p.a11y.buttonsAsDiv for p in a11y_pages)
    a11y_generic_links = sum(p.a11y.linksGeneric for p in a11y_pages)
    a11y_no_landmark = sum(1 for p in a11y_pages if not p.a11y.landmarksPresent)
    a11y_heading_issues = sum(1 for p in a11y_pages if p.a11y.headingOrderIssues or p.a11y.h1Count != 1)

    # responsive aggregates
    resp_pages = [p for p in pages if p.responsive is not None]
    resp_no_viewport = sum(1 for p in resp_pages if not p.responsive.hasViewportMeta)
    resp_block_zoom = sum(1 for p in resp_pages if p.responsive.viewportBlocksZoom)
    resp_no_media = sum(1 for p in resp_pages if p.responsive.cssMediaQueries == 0)

    # --- SECURITY ----------------------------------------------------------
    sec = 100.0
    if not https:
        sec -= 35
    if mixed_content:
        sec -= min(25, mixed_content * 5)
    if status_5xx:
        sec -= min(15, status_5xx * 5)
    # (header/RGPD checks aren't in the crawl yet — leave headroom for LLM)

    # --- SEO ---------------------------------------------------------------
    seo = 100.0
    seo -= min(20, _ratio(pages_no_title, n_pages) * 60)
    seo -= min(20, _ratio(pages_no_meta, n_pages) * 50)
    seo -= min(12, _ratio(pages_no_h1, n_pages) * 40)
    seo -= min(10, _ratio(title_too_long, n_pages) * 25)
    seo -= min(15, (dup_titles + dup_meta) * 1.5)
    seo -= min(15, _ratio(pages_no_canonical, n_pages) * 30)
    seo -= min(10, broken_links * 1.5)
    seo -= min(8, status_4xx * 1.0)
    seo -= min(8, redirect_chains * 2)
    seo -= min(8, orphans * 1.0)
    seo -= min(8, duplicates * 1.0)
    if not has_schema:
        seo -= 5

    # --- UX ----------------------------------------------------------------
    ux = 100.0
    ux -= min(15, _ratio(resp_no_viewport, max(len(resp_pages), 1)) * 50) if resp_pages else 0
    ux -= min(10, resp_block_zoom * 3)
    ux -= min(10, _ratio(resp_no_media, max(len(resp_pages), 1)) * 20) if resp_pages else 0
    # accessibility weighs into UX too
    ux -= min(15, _ratio(imgs_no_alt, max(imgs_total, 1)) * 40)
    ux -= min(8, a11y_div_buttons * 2)
    ux -= min(8, a11y_generic_links * 0.5)
    ux -= min(8, _ratio(a11y_no_landmark, max(len(a11y_pages), 1)) * 20) if a11y_pages else 0
    ux -= min(8, _ratio(a11y_heading_issues, max(len(a11y_pages), 1)) * 16) if a11y_pages else 0

    # --- CONTENT -----------------------------------------------------------
    content = 100.0
    content -= min(25, _ratio(thin_pages, n_pages) * 50)
    content -= min(15, duplicates * 2)
    content -= min(10, _ratio(pages_no_meta, n_pages) * 25)  # missing meta = also content
    content -= min(8, _ratio(imgs_no_alt, max(imgs_total, 1)) * 16)
    # (E-E-A-T / freshness aren't in the crawl — LLM headroom)

    # --- PERFORMANCE -------------------------------------------------------
    if perf and perf.source != "unavailable":
        # Use the Lighthouse score if available; else derive from metric ratings.
        if perf.performanceScore is not None:
            performance = float(perf.performanceScore)
        else:
            ratings = [m.rating for m in (perf.metrics or []) if m.rating]
            if ratings:
                good = sum(1 for r in ratings if r == "good")
                ni = sum(1 for r in ratings if r == "needs-improvement")
                performance = 100.0 * (good + 0.5 * ni) / len(ratings)
            else:
                performance = 70.0  # data present but no usable ratings
        # penalise heavy pages / no lazy loading lightly
        heavy_imgs = sum(
            1 for p in pages for i in p.images
            if not i.isInlineSvg and i.loading != "lazy"
        )
        legacy_imgs = sum(
            1 for p in pages for i in p.images
            if i.fileFormat in ("jpg", "jpeg", "png")
        )
        performance -= min(6, _ratio(heavy_imgs, max(imgs_total, 1)) * 8)
        performance -= min(4, _ratio(legacy_imgs, max(imgs_total, 1)) * 5)
    else:
        # No field data — neutral-ish, LLM marks it as an estimate.
        performance = 60.0

    # --- BUSINESS / conversion / local / AI search -------------------------
    biz = 100.0
    if not has_schema:
        biz -= 12
    if not getattr(crawl, "hasLlmsTxt", False):
        biz -= 6
    # AI crawlers blocked?
    if crawl.geoAudit if hasattr(crawl, "geoAudit") else False:
        pass  # geoAudit not on CrawlData; handled elsewhere
    # thin homepage / no clear value prop is hard to detect statically — headroom
    biz -= min(10, _ratio(thin_pages, n_pages) * 15)

    return {
        "security": _clamp(sec),
        "seo": _clamp(seo),
        "ux": _clamp(ux),
        "content": _clamp(content),
        "performance": _clamp(performance),
        "business": _clamp(biz),
    }


_AXIS_LABELS = {
    "security": "Sécurité",
    "seo": "SEO",
    "ux": "UX",
    "content": "Contenu",
    "performance": "Performance",
    "business": "Business",
}


def format_base_scores_block(scores: dict[str, int]) -> str:
    """Human-readable block for the analyzer prompt: tells the LLM the
    factual base scores and that it may adjust each by ±10 with a reason."""
    lines = [
        "## Scores de base (calculés à partir des faits du crawl — NE PAS recalculer de zéro)",
        "Voici le score 0-100 par axe dérivé déterministiquement des données collectées "
        "(codes HTTP, titres/meta dupliqués ou manquants, ratio texte/HTML, canonicals, "
        "images sans alt, Core Web Vitals, accessibilité, maillage interne, schema, llms.txt).",
        "",
    ]
    for axis, label in _AXIS_LABELS.items():
        lines.append(f"- {label} ({axis}) : base = {scores[axis]}/100")
    lines.append("")
    lines.append(
        "RÈGLE : pour chaque axe, repars de ce score de base. Tu peux l'AJUSTER de "
        "±10 points MAXIMUM si ton expertise fait apparaître un facteur que le calcul "
        "ne capte pas (ex. E-E-A-T faible, headers sécurité absents, valeur business "
        "peu claire), et tu DOIS alors le justifier dans le verdict de l'axe. Hors de "
        "cet intervalle de ±10, garde le score de base. Cela garantit que deux audits "
        "du même site donnent le même score."
    )
    return "\n".join(lines)


def clamp_to_base(llm_scores: dict, base_scores: dict[str, int], delta: int = 10) -> dict[str, int]:
    """After the LLM responds, clamp each axis score to base ± delta so a
    hallucinated swing can't get through."""
    out: dict[str, int] = {}
    for axis, base in base_scores.items():
        v = llm_scores.get(axis)
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = base
        out[axis] = max(0, min(100, max(base - delta, min(base + delta, v))))
    return out
