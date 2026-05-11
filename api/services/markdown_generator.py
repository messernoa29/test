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
