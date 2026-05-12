"""Markdown export for an audit result — optimised for Notion import.

Notion's "Import → Markdown" turns `<details><summary>…</summary>…</details>`
into a collapsible toggle, ATX headings into headings (collapsible by
default in Notion), `- [ ]` into checkboxes, `> …` into quotes, and small
markdown tables into tables. So instead of one endless wall, we put the
summary + quick wins up front (visible) and fold every heavy section into
a toggle that the reader expands on demand. Big per-URL tables are kept
short here (a digest + "see the Excel export") because Notion renders
300-row markdown tables one row at a time, which is heavy on import.
"""

from __future__ import annotations

from api.models import AuditResult, Finding, PageAnalysis

_SECTION_TITLES = {
    "security": "Sécurité & conformité",
    "seo": "SEO technique & on-page",
    "ux": "Expérience utilisateur",
    "content": "Contenu & E-E-A-T",
    "performance": "Performance (Core Web Vitals)",
    "business": "Conversion & opportunités business",
}

_SEVERITY_EMOJI = {
    "critical": "🔴",
    "warning": "🟠",
    "info": "🔵",
    "ok": "🟢",
    "missing": "⚪️",
}
_SEVERITY_LABEL = {
    "critical": "Critique",
    "warning": "À corriger",
    "info": "Pour info",
    "ok": "OK",
    "missing": "Absent",
}


def _esc(text: object) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


class _MD:
    """Tiny builder that knows how to open/close Notion-friendly toggles."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, *ls: str) -> None:
        self.lines.extend(ls)

    def blank(self) -> None:
        self.lines.append("")

    def open_toggle(self, summary: str) -> None:
        # A blank line before/inside <details> is required for Notion/most
        # renderers to parse the inner markdown.
        self.lines.append(f"<details>")
        self.lines.append(f"<summary>{summary}</summary>")
        self.lines.append("")

    def close_toggle(self) -> None:
        self.lines.append("")
        self.lines.append("</details>")
        self.lines.append("")

    def render(self) -> str:
        return "\n".join(self.lines).rstrip() + "\n"


def _finding_lines(f: Finding) -> list[str]:
    emoji = _SEVERITY_EMOJI.get(f.severity, "•")
    label = _SEVERITY_LABEL.get(f.severity, f.severity)
    out = [f"**{emoji} {f.title}** — *{label}*", ""]
    if f.description:
        out += [f.description, ""]
    meta = []
    if f.impact:
        meta.append(f"Impact : {f.impact}")
    if f.effort:
        meta.append(f"Effort : {f.effort}")
    if meta:
        out += [" · ".join(meta), ""]
    if f.evidence:
        out += [f"> Preuve : {f.evidence}", ""]
    if f.recommendation:
        out += [f"_Objectif :_ {f.recommendation}", ""]
    if f.actions:
        out.append("À faire :")
        for a in f.actions:
            out.append(f"- [ ] {a}")
        out.append("")
    if f.reference:
        out += [f"_Réf : {f.reference}_", ""]
    return out


def _page_lines(p: PageAnalysis) -> list[str]:
    out: list[str] = []
    if getattr(p, "representsCount", 0):
        n = p.representsCount + 1
        pat = f" ({p.representsPattern})" if p.representsPattern else ""
        out.append(f"> **Page type** — cette analyse vaut pour {n} pages au même gabarit{pat}.")
        if p.representsSampleUrls:
            out.append(f"> Exemples : {', '.join(p.representsSampleUrls[:4])}")
        out.append("")
    bits = [f"Statut **{p.status}**"]
    if p.title:
        bits.append(f"Title ({p.titleLength}c) : {p.title}")
    if p.h1:
        bits.append(f"H1 : {p.h1}")
    bits.append(
        f"Meta ({p.metaLength}c) : {p.metaDescription}" if p.metaDescription
        else "Meta : *absente*"
    )
    for b in bits:
        out.append(f"- {b}")
    t = p.technical
    if t is not None:
        canon = ("absent" if t.canonical is None else "auto-réf" if t.canonicalIsSelf else f"→ {t.canonical}")
        out.append(
            "- _Technique :_ "
            + " · ".join([
                f"HTTP {t.statusCode}" if t.statusCode is not None else "HTTP —",
                f"profondeur {t.depth}" if t.depth is not None else "prof. —",
                f"{t.wordCount} mots",
                f"ratio {round(t.textRatio*100)}%" if t.htmlBytes else "ratio —",
                f"liens {t.internalLinksOut}/{t.externalLinksOut}",
                f"img {t.imagesCount} (sans alt {t.imagesWithoutAlt})",
                f"canonical {canon}",
                f"robots {t.robotsMeta or '—'}",
                f"lang {t.htmlLang or '—'}",
                "viewport présent" if t.hasViewportMeta else "viewport ABSENT",
                "mixed content OUI" if t.hasMixedContent else "mixed non",
                f"schema {', '.join(t.schemaTypes) if t.schemaTypes else '—'}",
            ])
        )
        if t.redirectChain:
            out.append(f"- _Redirections :_ {' → '.join(t.redirectChain)}")
        if t.issues:
            out.append(f"- _Problèmes :_ {'; '.join(t.issues)}")
        if t.suggestedSchema:
            out += ["", f"Schema.org suggéré ({t.suggestedSchemaType}) — à coller dans le `<head>` :", "",
                    "```html", '<script type="application/ld+json">', t.suggestedSchema, "</script>", "```", ""]
    if p.missingKeywords:
        out += ["", f"Mots-clés cibles manquants : {', '.join(p.missingKeywords)}"]
    if p.recommendation:
        rec = p.recommendation
        out += ["", "Réécriture proposée :"]
        if rec.title:
            out.append(f"- [ ] Title → `{rec.title}`")
        if rec.h1:
            out.append(f"- [ ] H1 → `{rec.h1}`")
        if rec.meta:
            out.append(f"- [ ] Meta → `{rec.meta}`")
        for a in rec.actions or []:
            out.append(f"- [ ] {a}")
    if p.findings:
        out.append("")
        for f in p.findings:
            out += _finding_lines(f)
    return out


def generate_markdown(audit: AuditResult, *, agency_name: str | None = None) -> str:
    m = _MD()
    m.add(f"# Audit web — {audit.domain}")
    m.blank()
    if agency_name:
        m.add(f"_Réalisé par {agency_name}_", "")
    m.add(
        f"- **URL** : {audit.url}",
        f"- **Date** : {audit.createdAt[:10]}",
        f"- **Score global** : {audit.globalScore}/100 — {audit.globalVerdict}",
        f"- **Points critiques** : {audit.criticalCount} · **À corriger** : {audit.warningCount}",
    )
    cov = audit.crawlCoverage
    if cov is not None and cov.requestedMaxPages:
        suffix = (
            " — limite atteinte, augmentez la profondeur pour un crawl complet"
            if cov.cappedByLimit else " — crawl complet" if cov.cappedBySite else ""
        )
        extra = (f" sur {cov.discoveredUrlCount} URLs trouvées"
                 if cov.discoveredUrlCount > cov.crawledPageCount else "")
        det = (f" · {cov.detailedPageCount} analysées en détail par l'IA"
               if cov.detailedPageCount and cov.detailedPageCount < cov.crawledPageCount else "")
        m.add(f"- **Couverture** : {cov.crawledPageCount} pages crawlées{extra}{det} "
              f"(profondeur demandée : {cov.requestedMaxPages}){suffix}")
    m.blank()

    # Scores per axis — small table, stays visible.
    m.add("## Scores par axe", "", "| Axe | Score |", "| --- | --- |")
    for sec, score in audit.scores.items():
        m.add(f"| {_esc(_SECTION_TITLES.get(sec, sec))} | {score}/100 |")
    m.blank()

    # Quick wins — the most important block, stays visible.
    wins = [w for w in (audit.quickWins or []) if isinstance(w, str) and w.strip()]
    if wins:
        m.add("## Quick wins (à faire en premier)", "")
        for q in wins:
            m.add(f"- [ ] {q}")
        m.blank()

    # --- Everything below is folded into toggles ---------------------------

    # Recommandations par axe — one toggle, each axis a nested toggle.
    actionable = [s for s in audit.sections if any(
        f.severity in ("critical", "warning") for f in s.findings)]
    clean = [s for s in audit.sections if s not in actionable]
    if actionable:
        m.open_toggle(f"📋 Recommandations par axe ({len(actionable)} axe(s) avec actions)")
        for s in actionable:
            crit = sum(1 for f in s.findings if f.severity == "critical")
            warn = sum(1 for f in s.findings if f.severity == "warning")
            badge = " · ".join(filter(None, [
                f"{crit} critique(s)" if crit else "", f"{warn} à corriger" if warn else ""]))
            m.open_toggle(f"{_SECTION_TITLES.get(s.section, s.title)} — {s.score}/100"
                          + (f"  ({badge})" if badge else ""))
            if s.verdict:
                m.add(f"> {s.verdict}", "")
            ordered = [f for f in s.findings if f.severity in ("critical", "warning")] + \
                      [f for f in s.findings if f.severity not in ("critical", "warning")]
            for f in ordered:
                m.add(*_finding_lines(f))
            m.close_toggle()
        m.close_toggle()
    if clean:
        m.add(f"_Axes sans point à corriger : {', '.join(_SECTION_TITLES.get(s.section, s.title) for s in clean)}._", "")

    # Per-page analysis — one toggle, each page nested.
    if audit.pages:
        m.open_toggle(f"📄 Analyse page par page ({len(audit.pages)} page(s))")
        for p in audit.pages:
            m.open_toggle(f"`{p.url}` — {p.status}")
            m.add(*_page_lines(p))
            m.close_toggle()
        m.close_toggle()

    # SXO
    sxo = audit.sxoAudit
    if sxo is not None and sxo.verdicts:
        m.open_toggle(f"🎯 SXO — type de page vs intention SERP ({sxo.mismatches} mismatch sur {sxo.evaluated})")
        m.add(sxo.note, "")
        for v in sxo.verdicts:
            lbl = {"ok": "OK", "info": "Léger écart", "warning": "Mismatch", "critical": "Mauvais format"}.get(v.severity, v.severity)
            m.add(f"**`{v.url}`** — {lbl}",
                  f"- Requête « {v.keyword} » · page : {v.pageType} · SERP dominante : {v.serpDominantType or '—'}")
            if v.recommendation:
                m.add(f"  - [ ] {v.recommendation}")
            m.blank()
        m.close_toggle()

    # Programmatic
    pg = audit.programmaticAudit
    if pg is not None and pg.isProgrammatic:
        m.open_toggle(f"🏭 Pages générées en masse — quality gates ({len(pg.groups)} groupe(s))")
        m.add("Google sanctionne le contenu généré à grande échelle sans valeur propre (Scaled Content Abuse, mars 2024).", "")
        for g in pg.groups:
            gl = {"PASS": "OK", "WARNING": "À renforcer", "HARD_STOP": "Risque pénalité"}.get(g.gate, g.gate)
            m.add(f"**`{g.pattern}`** — {gl}",
                  f"- {g.pageCount} pages · ~{g.avgWordCount} mots/page · unique ~{round(g.uniquenessRatio*100)}%")
            for n in g.notes:
                m.add(f"  - [ ] {n}")
            if g.sampleUrls:
                m.add(f"- Exemples : {', '.join(g.sampleUrls[:4])}")
            m.blank()
        m.close_toggle()

    # Accessibility + responsive — one toggle.
    a = audit.accessibilityAudit
    r = audit.responsiveAudit
    if a is not None or r is not None:
        title_bits = []
        if a is not None:
            title_bits.append(f"a11y {a.averageScore}/100")
        if r is not None and r.pagesWithHorizontalScroll:
            title_bits.append(f"{r.pagesWithHorizontalScroll} page(s) scroll horizontal")
        m.open_toggle("♿ Accessibilité & responsive" + (f" — {', '.join(title_bits)}" if title_bits else ""))
        if a is not None:
            m.add("### Accessibilité (WCAG)", f"- Score automatique moyen : {a.averageScore}/100")
            agg = []
            if a.pagesWithoutLang: agg.append(f"{a.pagesWithoutLang} sans `<html lang>`")
            if a.imagesWithoutAlt: agg.append(f"{a.imagesWithoutAlt} images sans alt")
            if a.formInputsWithoutLabel: agg.append(f"{a.formInputsWithoutLabel} champs sans label")
            if a.buttonsAsDiv: agg.append(f"{a.buttonsAsDiv} « boutons » en `<div>`")
            if a.linksGeneric: agg.append(f"{a.linksGeneric} liens non descriptifs")
            if a.pagesWithoutLandmarks: agg.append(f"{a.pagesWithoutLandmarks} sans `<main>`")
            if a.pagesWithHeadingIssues: agg.append(f"{a.pagesWithHeadingIssues} pages titres mal hiérarchisés")
            if agg:
                m.add("- " + " · ".join(agg))
            m.blank()
            if a.llmVerdict:
                m.add("**Verdict (IA)** :", a.llmVerdict, "")
            if a.llmTopFixes:
                m.add("Actions accessibilité prioritaires :")
                for f in a.llmTopFixes:
                    m.add(f"- [ ] {f}")
                m.blank()
            worst = [p for p in a.pageScores if p.score < 80][:12]
            if worst:
                m.add("Pages les moins accessibles :")
                for p in worst:
                    m.add(f"- `{p.url}` — {p.score}/100" + (f" : {'; '.join(p.issues)}" if p.issues else ""))
                m.blank()
        if r is not None:
            m.add("### Responsive / mobile")
            if r.summary:
                m.add(f"- {r.summary}")
            rb = []
            if r.pagesWithoutViewport: rb.append(f"{r.pagesWithoutViewport} sans `<meta viewport>`")
            if r.pagesBlockingZoom: rb.append(f"{r.pagesBlockingZoom} bloquent le zoom")
            rb.append(f"{r.pagesWithMediaQueries} avec media queries")
            rb.append(f"images responsive : {round(r.imagesWithSrcsetRatio*100)}%")
            if r.renderedPagesTested:
                rb.append(f"{r.renderedPagesTested} rendues à 375/768/1280px")
            m.add("- " + " · ".join(rb))
            for p in [pp for pp in r.pageResults if pp.issues]:
                m.add(f"- `{p.url}`")
                for iss in p.issues:
                    m.add(f"  - [ ] {iss}")
            m.blank()
        m.close_toggle()

    # GEO — one toggle.
    geo = audit.geoAudit
    if geo is not None:
        head = f"score {geo.averagePageScore}/100"
        if geo.queriesTested:
            head += f" · cité sur {geo.citedCount}/{geo.queriesTested} requêtes"
        m.open_toggle(f"🤖 GEO — citabilité par les IA — {head}")
        m.add(f"- Score de citabilité moyen : {geo.averagePageScore}/100",
              f"- /llms.txt : {'présent' if geo.hasLlmsTxt else 'absent'}", "")
        if geo.queryVerdicts:
            m.add("### Test de citabilité IA par requête", "")
            for v in geo.queryVerdicts:
                mk = "✅ cité" if v.likelyCited else "❌ pas cité"
                eng = f" ({', '.join(v.citingEngines)})" if v.citingEngines else ""
                m.add(f"- **« {v.query} »** — {mk}{eng} · {v.intent} · confiance {v.confidence}")
                if v.reason: m.add(f"  - {v.reason}")
                if v.competitorsCitedInstead: m.add(f"  - Cités à la place : {', '.join(v.competitorsCitedInstead)}")
                if v.improvement: m.add(f"  - [ ] {v.improvement}")
            m.blank()
        if geo.siteWeaknesses:
            m.add("### À corriger (site)")
            for s in geo.siteWeaknesses:
                m.add(f"- [ ] {s}")
            m.blank()
        if geo.siteStrengths:
            m.add("### Points forts (site)")
            for s in geo.siteStrengths:
                m.add(f"- {s}")
            m.blank()
        if geo.aiCrawlerStatus:
            m.add("### Crawlers AI dans robots.txt")
            for ua, st in geo.aiCrawlerStatus.items():
                m.add(f"- {ua} : {st}")
            m.blank()
        worst_geo = [p for p in geo.pageScores if p.score < 70][:15]
        if worst_geo:
            m.add("### Pages les moins citables")
            for ps in worst_geo:
                m.add(f"- `{ps.url}` — {ps.score}/100")
                for s in ps.weaknesses:
                    m.add(f"  - [ ] {s}")
            m.blank()
        m.close_toggle()

    # Cultural
    ca = audit.culturalAudit
    if ca is not None and ca.isMultilingual:
        m.open_toggle(f"🌍 Adaptation culturelle (multilingue : {', '.join(ca.detectedLocales)})")
        for loc in ca.locales:
            m.add(f"### {loc.label} ({loc.locale}) — {loc.pagesWithIssues}/{loc.pagesCount} pages avec écart",
                  f"- Format nombre attendu : {loc.expectedNumberFormat} · Date : {loc.expectedDateFormat}")
            if loc.issueExamples:
                for pi in loc.issueExamples:
                    m.add(f"- `{pi.url}`")
                    for iss in pi.issues:
                        m.add(f"  - [ ] {iss}")
            else:
                m.add("- Aucun écart détecté.")
            m.blank()
        m.close_toggle()

    # Visibility — one toggle (tables stay short).
    v = audit.visibilityEstimate
    if v is not None:
        traffic = (v.trafficRange or (f"~{v.estimatedMonthlyOrganicTraffic} visites/mois"
                                      if v.estimatedMonthlyOrganicTraffic is not None else "—"))
        m.open_toggle(f"📈 Visibilité organique (estimation) — {traffic}")
        m.add(f"> {v.disclaimer}", "", f"- Trafic organique estimé : {traffic}")
        if v.estimatedRankingKeywordsCount is not None:
            m.add(f"- Mots-clés positionnés (estimation) : ~{v.estimatedRankingKeywordsCount}")
        if v.summary:
            m.add(f"- Synthèse : {v.summary}")
        m.blank()
        if v.topKeywords:
            m.add("### Mots-clés probablement positionnés", "",
                  "| Mot-clé | Volume est. | Position est. | Intention | Page |",
                  "| --- | --- | --- | --- | --- |")
            for k in v.topKeywords[:25]:
                m.add(f"| {_esc(k.keyword)} | {k.estimatedMonthlyVolume if k.estimatedMonthlyVolume is not None else '—'} "
                      f"| {k.estimatedPosition if k.estimatedPosition is not None else '—'} | {_esc(k.intent)} | {_esc(k.rankingUrl or '—')} |")
            m.blank()
        if v.opportunities:
            m.add("### Opportunités de mots-clés", "",
                  "| Mot-clé | Volume est. | Difficulté | Page à viser | Pourquoi |",
                  "| --- | --- | --- | --- | --- |")
            for k in v.opportunities[:25]:
                m.add(f"| {_esc(k.keyword)} | {k.estimatedMonthlyVolume if k.estimatedMonthlyVolume is not None else '—'} "
                      f"| {_esc(k.difficulty)} | {_esc(k.suggestedPage)} | {_esc(k.rationale)} |")
            m.blank()
        if v.competitorsLikelyOutranking:
            m.add("### Concurrents qui dominent ces SERP", "")
            for c in v.competitorsLikelyOutranking:
                m.add(f"- {c}")
            m.blank()
        m.close_toggle()

    # Technical crawl — one toggle, digest only (the full per-URL table lives
    # in the Excel export; a 300-row markdown table is painful to import).
    tc = audit.technicalCrawl
    if tc and tc.pagesCrawled:
        m.open_toggle(f"🔧 Crawl technique — {tc.pagesCrawled} URLs")
        m.add(f"- URLs crawlées : {tc.pagesCrawled} · indexables : {tc.indexablePages} · "
              f"non-indexables : {tc.nonIndexablePages} · profondeur max : {tc.maxDepth} clics")
        if tc.statusCounts:
            m.add("- Codes HTTP : " + ", ".join(f"{k}×{vv}" for k, vv in sorted(tc.statusCounts.items())))
        m.blank()
        m.add("_Le tableau complet URL par URL est dans le fichier Excel exporté à part._", "")

        def _grp(name: str, groups: list) -> None:
            if not groups:
                return
            m.add(f"### {name} ({len(groups)})")
            for g in groups[:10]:
                m.add(f"- {len(g)} pages : {', '.join(g[:4])}{' …' if len(g) > 4 else ''}")
            m.blank()

        def _lst(name: str, urls: list) -> None:
            if not urls:
                return
            m.add(f"### {name} ({len(urls)})")
            for u in urls[:25]:
                m.add(f"- [ ] {u}")
            if len(urls) > 25:
                m.add(f"- … +{len(urls) - 25}")
            m.blank()

        _grp("Titres dupliqués", tc.duplicateTitles)
        _grp("Meta descriptions dupliquées", tc.duplicateMetaDescriptions)
        _grp("H1 dupliqués", tc.duplicateH1s)
        _lst("Pages sans <title>", tc.missingTitles)
        _lst("Pages sans meta description", tc.missingMetaDescriptions)
        _lst("Pages sans H1", tc.missingH1)
        _lst("Titres trop longs (> 60c)", tc.titleTooLong)
        _lst("Titres trop courts (< 30c)", tc.titleTooShort)
        _lst("Meta trop longues (> 160c)", tc.metaTooLong)
        _lst("Pages à faible ratio texte/HTML (< 10%)", tc.lowTextRatioPages)
        _lst("Liens internes cassés (cibles 4xx/5xx)", tc.brokenInternalLinks)
        m.close_toggle()

    # Missing pages — short table, one toggle.
    if audit.missingPages:
        m.open_toggle(f"➕ Pages à créer ({len(audit.missingPages)})")
        m.add("| URL suggérée | Priorité | Pourquoi | Volume estimé |", "| --- | --- | --- | --- |")
        for mp in audit.missingPages:
            vol = mp.estimatedSearchVolume if mp.estimatedSearchVolume is not None else "—"
            m.add(f"| {_esc(mp.url)} | {_esc(mp.priority)} | {_esc(mp.reason)} | {vol} |")
        m.close_toggle()

    return m.render()
