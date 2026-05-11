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
