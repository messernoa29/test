"""Markdown export for an audit result — Notion / Obsidian friendly.

Notion's "Import → Markdown" understands: ATX headings, tables, `- [ ]`
checkboxes, blockquotes, code spans, bold/italic. We lean on those so a
pasted/imported file becomes a usable action plan with checkboxes the
agency can tick off as it ships fixes.
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
    """Escape pipe chars so table cells don't break."""
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def _finding_block(f: Finding) -> list[str]:
    emoji = _SEVERITY_EMOJI.get(f.severity, "•")
    label = _SEVERITY_LABEL.get(f.severity, f.severity)
    lines: list[str] = [f"#### {emoji} {f.title}  *( {label} )*", ""]
    if f.description:
        lines.append(f.description)
        lines.append("")
    meta_bits = []
    if f.impact:
        meta_bits.append(f"**Impact** : {f.impact}")
    if f.effort:
        meta_bits.append(f"**Effort** : {f.effort}")
    if meta_bits:
        lines.append(" · ".join(meta_bits))
        lines.append("")
    if f.evidence:
        lines.append(f"> Preuve observée : {f.evidence}")
        lines.append("")
    if f.recommendation:
        lines.append(f"**Objectif** : {f.recommendation}")
        lines.append("")
    if f.actions:
        lines.append("**À faire :**")
        for a in f.actions:
            lines.append(f"- [ ] {a}")
        lines.append("")
    if f.reference:
        lines.append(f"_Référence : {f.reference}_")
        lines.append("")
    return lines


def _page_block(p: PageAnalysis) -> list[str]:
    lines: list[str] = [f"### `{p.url}`", ""]
    if getattr(p, "representsCount", 0):
        n = p.representsCount + 1
        pat = f" ({p.representsPattern})" if p.representsPattern else ""
        lines.append(f"> **Page type** — cette analyse vaut pour {n} pages au même gabarit{pat}.")
        if p.representsSampleUrls:
            lines.append(f"> Exemples : {', '.join(p.representsSampleUrls[:4])}")
        lines.append("")
    status_bits = [f"Statut : **{p.status}**"]
    if p.title:
        status_bits.append(f"Title ({p.titleLength} car.) : {p.title}")
    if p.h1:
        status_bits.append(f"H1 : {p.h1}")
    if p.metaDescription is not None:
        status_bits.append(f"Meta ({p.metaLength} car.) : {p.metaDescription}")
    elif p.metaDescription is None:
        status_bits.append("Meta description : *absente*")
    for b in status_bits:
        lines.append(f"- {b}")
    lines.append("")
    t = p.technical
    if t is not None:
        canon = (
            "absent" if t.canonical is None
            else "auto-référent" if t.canonicalIsSelf
            else f"→ {t.canonical}"
        )
        tech_bits = [
            f"HTTP {t.statusCode}" if t.statusCode is not None else "HTTP —",
            f"profondeur {t.depth}" if t.depth is not None else "profondeur —",
            f"{t.wordCount} mots",
            f"ratio texte/HTML {round(t.textRatio*100)}%" if t.htmlBytes else "ratio —",
            f"liens int/ext {t.internalLinksOut}/{t.externalLinksOut}",
            f"images {t.imagesCount} (sans alt {t.imagesWithoutAlt})",
            f"canonical {canon}",
            f"robots {t.robotsMeta or '—'}",
            f"lang {t.htmlLang or '—'}",
            f"hreflang {', '.join(t.hreflangLangs) if t.hreflangLangs else '—'}",
            "viewport présent" if t.hasViewportMeta else "viewport ABSENT",
            "mixed content OUI" if t.hasMixedContent else "mixed content non",
            f"OG {'og:title' if t.ogTitle else 'absent'}",
            f"schema {', '.join(t.schemaTypes) if t.schemaTypes else '—'}",
        ]
        lines.append("- _Technique :_ " + " · ".join(tech_bits))
        if t.redirectChain:
            lines.append(f"- _Redirections :_ {' → '.join(t.redirectChain)}")
        if t.issues:
            lines.append(f"- _Problèmes crawl :_ {'; '.join(t.issues)}")
        lines.append("")
        if t.suggestedSchema:
            lines.append(
                f"**Schema.org suggéré** ({t.suggestedSchemaType}) — à coller dans le `<head>` :"
            )
            lines.append("")
            lines.append("```html")
            lines.append('<script type="application/ld+json">')
            lines.append(t.suggestedSchema)
            lines.append("</script>")
            lines.append("```")
            lines.append("")
    if p.missingKeywords:
        lines.append(f"Mots-clés cibles manquants : {', '.join(p.missingKeywords)}")
        lines.append("")
    if p.recommendation:
        rec = p.recommendation
        lines.append("**Réécriture proposée :**")
        if rec.title:
            lines.append(f"- [ ] Title → `{rec.title}`")
        if rec.h1:
            lines.append(f"- [ ] H1 → `{rec.h1}`")
        if rec.meta:
            lines.append(f"- [ ] Meta description → `{rec.meta}`")
        for a in rec.actions or []:
            lines.append(f"- [ ] {a}")
        lines.append("")
    for f in p.findings:
        lines.extend(_finding_block(f))
    return lines


def generate_markdown(audit: AuditResult, *, agency_name: str | None = None) -> str:
    L: list[str] = []
    title = f"Audit web — {audit.domain}"
    L.append(f"# {title}")
    L.append("")
    if agency_name:
        L.append(f"_Réalisé par {agency_name}_")
        L.append("")
    L.append(f"- **URL** : {audit.url}")
    L.append(f"- **Date** : {audit.createdAt[:10]}")
    L.append(f"- **Score global** : {audit.globalScore}/100 — {audit.globalVerdict}")
    L.append(f"- **Points critiques** : {audit.criticalCount} · **À corriger** : {audit.warningCount}")
    cov = audit.crawlCoverage
    if cov is not None and cov.requestedMaxPages:
        suffix = (
            " — limite atteinte, relancez avec une profondeur supérieure pour un crawl technique complet"
            if cov.cappedByLimit
            else " — crawl complet" if cov.cappedBySite else ""
        )
        extra = (
            f" sur {cov.discoveredUrlCount} URLs trouvées"
            if cov.discoveredUrlCount > cov.crawledPageCount else ""
        )
        detail = (
            f" · {cov.detailedPageCount} analysées en détail par l'IA"
            if cov.detailedPageCount and cov.detailedPageCount < cov.crawledPageCount else ""
        )
        L.append(
            f"- **Couverture du crawl** : {cov.crawledPageCount} pages crawlées techniquement{extra}{detail} "
            f"(profondeur demandée : {cov.requestedMaxPages}){suffix}"
        )
    L.append("")

    # Scores table
    L.append("## Scores par axe")
    L.append("")
    L.append("| Axe | Score |")
    L.append("| --- | --- |")
    for sec, score in audit.scores.items():
        L.append(f"| {_esc(_SECTION_TITLES.get(sec, sec))} | {score}/100 |")
    L.append("")

    # Quick wins
    if audit.quickWins:
        L.append("## Quick wins (à faire en premier)")
        L.append("")
        for q in audit.quickWins:
            L.append(f"- [ ] {q}")
        L.append("")

    # Sections
    for section in audit.sections:
        sec_title = _SECTION_TITLES.get(section.section, section.title or section.section)
        L.append(f"## {sec_title} — {section.score}/100")
        L.append("")
        if section.verdict:
            L.append(f"> {section.verdict}")
            L.append("")
        if not section.findings:
            L.append("_Aucun point relevé._")
            L.append("")
            continue
        for f in section.findings:
            L.extend(_finding_block(f))

    # Per-page analysis
    if audit.pages:
        L.append("## Analyse page par page")
        L.append("")
        for p in audit.pages:
            L.extend(_page_block(p))

    # SXO — page-type vs SERP-intent
    sxo = audit.sxoAudit
    if sxo is not None and sxo.verdicts:
        L.append("## SXO — type de page vs intention SERP")
        L.append("")
        L.append(sxo.note)
        L.append("")
        L.append(f"{sxo.evaluated} pages évaluées · {sxo.mismatches} mismatch(es)")
        L.append("")
        for v in sxo.verdicts:
            sev_lbl = {"ok": "OK", "info": "Léger écart", "warning": "Mismatch", "critical": "Mauvais format"}.get(v.severity, v.severity)
            L.append(f"### `{v.url}` — {sev_lbl}")
            L.append(
                f"- Requête : « {v.keyword} » · votre page : {v.pageType} · "
                f"SERP dominante : {v.serpDominantType or '—'}"
            )
            if v.recommendation:
                L.append(f"  - [ ] {v.recommendation}")
            L.append("")

    # Programmatic SEO quality gates
    pg = audit.programmaticAudit
    if pg is not None and pg.isProgrammatic:
        L.append("## Pages générées en masse (quality gates)")
        L.append("")
        L.append(
            "Google sanctionne le contenu généré à grande échelle sans valeur "
            "propre (Scaled Content Abuse, mars 2024)."
        )
        L.append("")
        for g in pg.groups:
            gate_lbl = {"PASS": "OK", "WARNING": "À renforcer", "HARD_STOP": "Risque pénalité"}.get(g.gate, g.gate)
            L.append(f"### `{g.pattern}` — {gate_lbl}")
            L.append(
                f"- {g.pageCount} pages · ~{g.avgWordCount} mots/page · "
                f"contenu unique estimé {round(g.uniquenessRatio * 100)}% "
                f"(boilerplate {round(g.boilerplateRatio * 100)}%)"
            )
            for n in g.notes:
                L.append(f"  - [ ] {n}")
            if g.sampleUrls:
                L.append(f"- Exemples : {', '.join(g.sampleUrls[:4])}")
            L.append("")

    # Accessibility (WCAG)
    a = audit.accessibilityAudit
    if a is not None:
        L.append("## Accessibilité (WCAG)")
        L.append("")
        L.append(f"- Score automatique moyen : {a.averageScore}/100")
        agg_bits = []
        if a.pagesWithoutLang:
            agg_bits.append(f"{a.pagesWithoutLang} page(s) sans `<html lang>`")
        if a.imagesWithoutAlt:
            agg_bits.append(f"{a.imagesWithoutAlt} image(s) sans alt")
        if a.formInputsWithoutLabel:
            agg_bits.append(f"{a.formInputsWithoutLabel} champ(s) sans label")
        if a.buttonsAsDiv:
            agg_bits.append(f"{a.buttonsAsDiv} « bouton(s) » en `<div>`")
        if a.linksGeneric:
            agg_bits.append(f"{a.linksGeneric} lien(s) non descriptif(s)")
        if a.pagesWithoutLandmarks:
            agg_bits.append(f"{a.pagesWithoutLandmarks} page(s) sans `<main>`")
        if a.pagesWithHeadingIssues:
            agg_bits.append(f"{a.pagesWithHeadingIssues} page(s) à titres mal hiérarchisés")
        if agg_bits:
            L.append("- " + " · ".join(agg_bits))
        L.append("")
        if a.llmVerdict:
            L.append("### Verdict (analyse IA)")
            L.append("")
            L.append(a.llmVerdict)
            L.append("")
        if a.llmTopFixes:
            L.append("### Actions accessibilité prioritaires")
            for f in a.llmTopFixes:
                L.append(f"- [ ] {f}")
            L.append("")
        worst = [p for p in a.pageScores if p.score < 80][:15]
        if worst:
            L.append("### Pages les moins accessibles")
            for p in worst:
                L.append(f"- `{p.url}` — {p.score}/100")
                for iss in p.issues:
                    L.append(f"  - {iss}")
            L.append("")

    # Responsive / mobile
    r = audit.responsiveAudit
    if r is not None:
        L.append("## Responsive / mobile")
        L.append("")
        if r.summary:
            L.append(f"- {r.summary}")
        rbits = []
        if r.pagesWithoutViewport:
            rbits.append(f"{r.pagesWithoutViewport} page(s) sans `<meta viewport>`")
        if r.pagesBlockingZoom:
            rbits.append(f"{r.pagesBlockingZoom} page(s) bloquant le zoom")
        rbits.append(f"{r.pagesWithMediaQueries} page(s) avec media queries")
        rbits.append(f"images responsive (srcset) : {round(r.imagesWithSrcsetRatio*100)}%")
        if r.renderedPagesTested:
            rbits.append(f"{r.renderedPagesTested} page(s) rendue(s) à 375/768/1280px")
            if r.pagesWithHorizontalScroll:
                rbits.append(f"{r.pagesWithHorizontalScroll} avec scroll horizontal")
        L.append("- " + " · ".join(rbits))
        L.append("")
        with_issues = [p for p in r.pageResults if p.issues]
        if with_issues:
            for p in with_issues:
                L.append(f"- `{p.url}`")
                for iss in p.issues:
                    L.append(f"  - [ ] {iss}")
            L.append("")

    # GEO (AI citability)
    geo = audit.geoAudit
    if geo is not None:
        L.append("## GEO — citabilité par les IA")
        L.append("")
        L.append(
            f"- Score de citabilité moyen : {geo.averagePageScore}/100"
        )
        L.append(f"- /llms.txt : {'présent' if geo.hasLlmsTxt else 'absent'}")
        if geo.queriesTested:
            L.append(
                f"- Test de citation IA : site probablement cité sur "
                f"{geo.citedCount}/{geo.queriesTested} requêtes testées"
            )
        L.append("")
        if geo.queryVerdicts:
            L.append("### Test de citabilité IA par requête")
            L.append("")
            for v in geo.queryVerdicts:
                mark = "✅ cité" if v.likelyCited else "❌ pas cité"
                eng = f" ({', '.join(v.citingEngines)})" if v.citingEngines else ""
                L.append(f"- **« {v.query} »** — {mark}{eng} · intention : {v.intent} · confiance : {v.confidence}")
                if v.reason:
                    L.append(f"  - {v.reason}")
                if v.competitorsCitedInstead:
                    L.append(f"  - Cités à la place : {', '.join(v.competitorsCitedInstead)}")
                if v.improvement:
                    L.append(f"  - [ ] {v.improvement}")
            L.append("")
        if geo.siteStrengths:
            L.append("### Points forts (site)")
            for s in geo.siteStrengths:
                L.append(f"- {s}")
            L.append("")
        if geo.siteWeaknesses:
            L.append("### À corriger (site)")
            for s in geo.siteWeaknesses:
                L.append(f"- [ ] {s}")
            L.append("")
        if geo.aiCrawlerStatus:
            L.append("### Crawlers AI dans robots.txt")
            for ua, st in geo.aiCrawlerStatus.items():
                L.append(f"- {ua} : {st}")
            L.append("")
        if geo.pageScores:
            L.append("### Citabilité par page (les plus faibles d'abord)")
            L.append("")
            for ps in geo.pageScores:
                L.append(f"- `{ps.url}` — {ps.score}/100")
                for s in ps.weaknesses:
                    L.append(f"  - [ ] {s}")
            L.append("")

    # Cultural adaptation (multilingual)
    ca = audit.culturalAudit
    if ca is not None and ca.isMultilingual:
        L.append("## Adaptation culturelle (site multilingue)")
        L.append("")
        L.append(f"Langues détectées : {', '.join(ca.detectedLocales)}")
        L.append("")
        for loc in ca.locales:
            L.append(
                f"### {loc.label} ({loc.locale}) — {loc.pagesWithIssues}/{loc.pagesCount} pages avec écart"
            )
            L.append(
                f"- Format nombre attendu : {loc.expectedNumberFormat} · Date : {loc.expectedDateFormat}"
            )
            if loc.issueExamples:
                for pi in loc.issueExamples:
                    L.append(f"- `{pi.url}`")
                    for iss in pi.issues:
                        L.append(f"  - [ ] {iss}")
            else:
                L.append("- Aucun écart détecté.")
            L.append("")

    # Visibility estimate (SEMrush-style, LLM-estimated)
    v = audit.visibilityEstimate
    if v is not None:
        L.append("## Visibilité organique (estimation)")
        L.append("")
        L.append(f"> {v.disclaimer}")
        L.append("")
        traffic = (
            v.trafficRange
            or (f"~{v.estimatedMonthlyOrganicTraffic} visites/mois"
                if v.estimatedMonthlyOrganicTraffic is not None else "—")
        )
        L.append(f"- Trafic organique estimé : {traffic}")
        if v.estimatedRankingKeywordsCount is not None:
            L.append(f"- Mots-clés positionnés (estimation) : ~{v.estimatedRankingKeywordsCount}")
        if v.summary:
            L.append(f"- Synthèse : {v.summary}")
        L.append("")
        if v.topKeywords:
            L.append("### Mots-clés probablement positionnés")
            L.append("")
            L.append("| Mot-clé | Volume est. | Position est. | Intention | Page | Note |")
            L.append("| --- | --- | --- | --- | --- | --- |")
            for k in v.topKeywords:
                L.append(
                    f"| {_esc(k.keyword)} | {k.estimatedMonthlyVolume if k.estimatedMonthlyVolume is not None else '—'} "
                    f"| {k.estimatedPosition if k.estimatedPosition is not None else '—'} | {_esc(k.intent)} "
                    f"| {_esc(k.rankingUrl or '—')} | {_esc(k.note)} |"
                )
            L.append("")
        if v.opportunities:
            L.append("### Opportunités de mots-clés")
            L.append("")
            L.append("| Mot-clé | Volume est. | Difficulté | Page à viser | Pourquoi |")
            L.append("| --- | --- | --- | --- | --- |")
            for k in v.opportunities:
                L.append(
                    f"| {_esc(k.keyword)} | {k.estimatedMonthlyVolume if k.estimatedMonthlyVolume is not None else '—'} "
                    f"| {_esc(k.difficulty)} | {_esc(k.suggestedPage)} | {_esc(k.rationale)} |"
                )
            L.append("")
        if v.competitorsLikelyOutranking:
            L.append("### Concurrents qui dominent probablement ces SERP")
            L.append("")
            for c in v.competitorsLikelyOutranking:
                L.append(f"- {c}")
            L.append("")

    # Technical crawl table (Screaming-Frog-style)
    tc = audit.technicalCrawl
    if tc and tc.pagesCrawled:
        L.append("## Crawl technique")
        L.append("")
        L.append(
            f"- URLs crawlées : {tc.pagesCrawled} · indexables : {tc.indexablePages} · "
            f"non-indexables : {tc.nonIndexablePages} · profondeur max : {tc.maxDepth} clics"
        )
        if tc.statusCounts:
            L.append(
                "- Codes HTTP : "
                + ", ".join(f"{k}×{v}" for k, v in sorted(tc.statusCounts.items()))
            )
        L.append("")

        def _md_group(name: str, groups: list) -> None:
            if not groups:
                return
            L.append(f"### {name} ({len(groups)})")
            for g in groups[:10]:
                L.append(f"- {len(g)} pages : {', '.join(g[:4])}{' …' if len(g) > 4 else ''}")
            L.append("")

        def _md_list(name: str, urls: list) -> None:
            if not urls:
                return
            L.append(f"### {name} ({len(urls)})")
            for u in urls[:30]:
                L.append(f"- [ ] {u}")
            if len(urls) > 30:
                L.append(f"- … +{len(urls) - 30}")
            L.append("")

        _md_group("Titres dupliqués", tc.duplicateTitles)
        _md_group("Meta descriptions dupliquées", tc.duplicateMetaDescriptions)
        _md_group("H1 dupliqués", tc.duplicateH1s)
        _md_list("Pages sans <title>", tc.missingTitles)
        _md_list("Pages sans meta description", tc.missingMetaDescriptions)
        _md_list("Pages sans H1", tc.missingH1)
        _md_list("Titres trop longs (> 60 car.)", tc.titleTooLong)
        _md_list("Titres trop courts (< 30 car.)", tc.titleTooShort)
        _md_list("Meta trop longues (> 160 car.)", tc.metaTooLong)
        _md_list("Pages à faible ratio texte/HTML (< 10%)", tc.lowTextRatioPages)
        _md_list("Liens internes cassés (cibles 4xx/5xx)", tc.brokenInternalLinks)

        # Full table
        L.append("### Tableau complet (une ligne par URL)")
        L.append("")
        L.append("| URL | Code | Prof. | Indexable | Title | Meta | H1 | Mots | Liens int/ext | Img (sans alt) | Problèmes |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in tc.rows:
            idx = "✓" if r.isIndexable else f"✗ ({r.indexabilityReason})"
            img = f"{r.imagesCount}" + (f" ({r.imagesWithoutAlt})" if r.imagesWithoutAlt else "")
            L.append(
                f"| {_esc(r.url)} | {r.statusCode or 'ERR'} | {r.depth if r.depth is not None else '—'} "
                f"| {idx} | {r.titleLength or '—'} | {r.metaDescLength or '—'} | {r.h1Count} "
                f"| {r.wordCount or '—'} | {r.internalLinksOut}/{r.externalLinksOut} | {img} "
                f"| {_esc('; '.join(r.issues)) or 'OK'} |"
            )
        L.append("")

    # Missing pages
    if audit.missingPages:
        L.append("## Pages à créer")
        L.append("")
        L.append("| URL suggérée | Priorité | Pourquoi | Volume estimé |")
        L.append("| --- | --- | --- | --- |")
        for mp in audit.missingPages:
            vol = mp.estimatedSearchVolume if mp.estimatedSearchVolume is not None else "—"
            L.append(
                f"| {_esc(mp.url)} | {_esc(mp.priority)} | {_esc(mp.reason)} | {vol} |"
            )
        L.append("")

    return "\n".join(L).rstrip() + "\n"
