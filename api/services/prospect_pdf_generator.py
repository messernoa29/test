"""Generate a polished PDF for a Prospect Sheet (pre-meeting sales brief).

Palette & typography mirror the audit PDF (docs/DESIGN.md §PDF, version claire).
Structure: cover → 1. Identité entreprise (+ groupe / maison-mère) →
2. Stack technique → 3. Persona, contacts & angles d'approche.

Layout guarantees:
- All widths derive from CONTENT_WIDTH.
- Every text size change lives in a ParagraphStyle (no inline <font size>).
- A dead source URL is shown with a ⚠️ marker (never removed).
"""

from __future__ import annotations

import html
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from api.models import (
    DetectedTech,
    ProspectContact,
    ProspectParentCompany,
    ProspectPersona,
    ProspectSheet,
)

# ---------------------------------------------------------------------------
# Geometry

PAGE_W, PAGE_H = A4
LEFT_M = 22 * mm
RIGHT_M = 22 * mm
TOP_M = 22 * mm
BOTTOM_M = 18 * mm
CONTENT_WIDTH = PAGE_W - LEFT_M - RIGHT_M

# ---------------------------------------------------------------------------
# Palette (DESIGN.md §3 version claire)

BG_PAGE = colors.HexColor("#F7F5F0")
BG_SURFACE = colors.HexColor("#EDEAE3")
BG_ELEVATED = colors.HexColor("#FFFFFF")
TEXT_PRIMARY = colors.HexColor("#1A1A17")
TEXT_SECONDARY = colors.HexColor("#6B6860")
TEXT_TERTIARY = colors.HexColor("#9E9B94")
ACCENT = colors.HexColor("#B8892D")
BORDER = colors.HexColor("#D9D4C8")
BORDER_STRONG = colors.HexColor("#BFB9A8")

CONF_COLORS: dict[str, colors.Color] = {
    "high": colors.HexColor("#059669"),
    "medium": colors.HexColor("#D97706"),
    "low": colors.HexColor("#9E9B94"),
}
CONF_LABEL = {"high": "fiable", "medium": "à recouper", "low": "signal faible"}
WARN_COLOR = colors.HexColor("#DC2626")

# ---------------------------------------------------------------------------
# Fonts (DM Serif Display / DM Sans / JetBrains Mono if present, else core)

FONT_DISPLAY = "Times-Roman"
FONT_DISPLAY_IT = "Times-Italic"
FONT_SANS = "Helvetica"
FONT_SANS_BD = "Helvetica-Bold"
FONT_MONO = "Courier"
FONT_MONO_BD = "Courier-Bold"


def _try_register(name: str, path: Path) -> bool:
    if not path.exists():
        return False
    try:
        pdfmetrics.registerFont(TTFont(name, str(path)))
        return True
    except Exception:
        return False


def _register_fonts() -> None:
    global FONT_DISPLAY, FONT_DISPLAY_IT, FONT_SANS, FONT_SANS_BD, FONT_MONO, FONT_MONO_BD
    fonts_dir = Path(
        os.getenv("PDF_FONTS_DIR", Path(__file__).resolve().parents[1] / "fonts")
    )
    if _try_register("DMSerifDisplay", fonts_dir / "DMSerifDisplay-Regular.ttf"):
        FONT_DISPLAY = "DMSerifDisplay"
    if _try_register("DMSerifDisplay-Italic", fonts_dir / "DMSerifDisplay-Italic.ttf"):
        FONT_DISPLAY_IT = "DMSerifDisplay-Italic"
    if _try_register("DMSans", fonts_dir / "DMSans-Regular.ttf"):
        FONT_SANS = "DMSans"
    if _try_register("DMSans-Medium", fonts_dir / "DMSans-Medium.ttf"):
        FONT_SANS_BD = "DMSans-Medium"
    if _try_register("JetBrainsMono", fonts_dir / "JetBrainsMono-Regular.ttf"):
        FONT_MONO = "JetBrainsMono"
    if _try_register("JetBrainsMono-Medium", fonts_dir / "JetBrainsMono-Medium.ttf"):
        FONT_MONO_BD = "JetBrainsMono-Medium"


_register_fonts()

# ---------------------------------------------------------------------------
# Helpers

_LIMIT_SHORT = 400
_LIMIT_LONG = 1600


def _esc(s: Optional[object], *, limit: Optional[int] = _LIMIT_SHORT) -> str:
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    s = s.strip()
    if limit is not None and len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return html.escape(s, quote=False)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "eyebrow": ParagraphStyle("eyebrow", parent=base, fontName=FONT_MONO_BD,
                                  fontSize=8.5, textColor=ACCENT, leading=11, spaceAfter=3),
        "cover_kicker": ParagraphStyle("cover_kicker", parent=base, fontName=FONT_DISPLAY_IT,
                                       fontSize=13, textColor=TEXT_SECONDARY, leading=16,
                                       spaceAfter=16),
        "cover_name": ParagraphStyle("cover_name", parent=base, fontName=FONT_DISPLAY,
                                     fontSize=30, textColor=TEXT_PRIMARY, leading=35, spaceAfter=6),
        "cover_meta": ParagraphStyle("cover_meta", parent=base, fontName=FONT_MONO,
                                     fontSize=10, textColor=TEXT_SECONDARY, leading=14),
        "cover_date": ParagraphStyle("cover_date", parent=base, fontName=FONT_SANS,
                                     fontSize=11, textColor=TEXT_SECONDARY, leading=15),
        "section_num": ParagraphStyle("section_num", parent=base, fontName=FONT_MONO_BD,
                                      fontSize=10, textColor=ACCENT, leading=12, spaceAfter=2),
        "section_title": ParagraphStyle("section_title", parent=base, fontName=FONT_DISPLAY,
                                        fontSize=22, textColor=TEXT_PRIMARY, leading=26, spaceAfter=10),
        "sub_title": ParagraphStyle("sub_title", parent=base, fontName=FONT_SANS_BD,
                                    fontSize=11, textColor=TEXT_PRIMARY, leading=15, spaceBefore=8,
                                    spaceAfter=4),
        "label": ParagraphStyle("label", parent=base, fontName=FONT_MONO_BD, fontSize=7.5,
                                textColor=TEXT_TERTIARY, leading=11),
        "body": ParagraphStyle("body", parent=base, fontName=FONT_SANS, fontSize=10,
                               textColor=TEXT_PRIMARY, leading=14),
        "body_sec": ParagraphStyle("body_sec", parent=base, fontName=FONT_SANS, fontSize=9.5,
                                   textColor=TEXT_SECONDARY, leading=13),
        "mono": ParagraphStyle("mono", parent=base, fontName=FONT_MONO, fontSize=9,
                               textColor=TEXT_PRIMARY, leading=12),
        "mono_sec": ParagraphStyle("mono_sec", parent=base, fontName=FONT_MONO, fontSize=8,
                                   textColor=TEXT_SECONDARY, leading=11),
        "bullet": ParagraphStyle("bullet", parent=base, fontName=FONT_SANS, fontSize=9.5,
                                 textColor=TEXT_PRIMARY, leading=13, leftIndent=10, spaceAfter=2),
        "name": ParagraphStyle("name", parent=base, fontName=FONT_SANS_BD, fontSize=10.5,
                                textColor=TEXT_PRIMARY, leading=14),
        "role": ParagraphStyle("role", parent=base, fontName=FONT_SANS, fontSize=9.5,
                               textColor=TEXT_SECONDARY, leading=13),
        "warn": ParagraphStyle("warn", parent=base, fontName=FONT_SANS, fontSize=8,
                               textColor=WARN_COLOR, leading=11),
        "empty": ParagraphStyle("empty", parent=base, fontName=FONT_DISPLAY_IT, fontSize=10,
                                textColor=TEXT_TERTIARY, leading=14),
    }


# ---------------------------------------------------------------------------
# Flowables


class AccentBand(Flowable):
    def __init__(self, width: float, height: float = 4, color: colors.Color = ACCENT) -> None:
        super().__init__()
        self.w, self.h, self.color = width, height, color

    def wrap(self, _aw: float, _ah: float) -> tuple[float, float]:
        return self.w, self.h

    def draw(self) -> None:
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, self.w, self.h, stroke=0, fill=1)


def _confidence_badge(conf: str, styles: dict) -> Table:
    conf = (conf or "medium").lower()
    color = CONF_COLORS.get(conf, CONF_COLORS["medium"])
    label = CONF_LABEL.get(conf, conf)
    p = Paragraph(
        f'<font color="#FFFFFF">{_esc(label.upper())}</font>',
        ParagraphStyle("b", parent=styles["label"], fontName=FONT_MONO_BD, fontSize=6.5,
                       textColor=colors.white, leading=8),
    )
    t = Table([[p]], colWidths=[60])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _tech_badge(tech: DetectedTech, styles: dict) -> Table:
    color = CONF_COLORS.get((tech.confidence or "medium").lower(), CONF_COLORS["medium"])
    label = Paragraph(_esc(tech.name, limit=60), ParagraphStyle(
        "tb", parent=styles["body"], fontName=FONT_SANS_BD, fontSize=8.5, leading=11))
    t = Table([[label]])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_SURFACE),
        ("LINEBELOW", (0, 0), (-1, -1), 2, color),
        ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _card(inner: list[Flowable], *, pad: float = 12) -> Table:
    t = Table([[inner]], colWidths=[CONTENT_WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_ELEVATED),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _kv_table(rows: list[tuple[str, str]], styles: dict) -> Optional[Table]:
    data = [(k, v) for k, v in rows if (v or "").strip()]
    if not data:
        return None
    body = [
        [Paragraph(_esc(k).upper(), styles["label"]), Paragraph(_esc(v, limit=600), styles["body"])]
        for k, v in data
    ]
    t = Table(body, colWidths=[34 * mm, CONTENT_WIDTH - 34 * mm - 24])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, BORDER),
    ]))
    return t


def _bullets(items: list[str], styles: dict) -> list[Flowable]:
    out: list[Flowable] = []
    for it in items:
        txt = (it or "").strip()
        if not txt:
            continue
        out.append(Paragraph("•&nbsp;&nbsp;" + _esc(txt, limit=600), styles["bullet"]))
    return out


def _source_line(source: str, source_url: str, source_url_ok: Optional[bool], styles: dict) -> Optional[Paragraph]:
    src = (source or "").strip()
    url = (source_url or "").strip()
    if not src and not url:
        return None
    bits: list[str] = []
    if src:
        bits.append(_esc(src, limit=120))
    if url:
        bits.append(_esc(url, limit=200))
    txt = "source : " + " — ".join(bits)
    if source_url_ok is False and url:
        txt += '  <font color="#DC2626">⚠ lien mort (404) — à vérifier manuellement</font>'
    return Paragraph(txt, styles["mono_sec"])


# ---------------------------------------------------------------------------
# Sections


def _cover(sheet: ProspectSheet, styles: dict) -> list[Flowable]:
    ident = sheet.identity
    name = (ident.name if ident else "") or sheet.domain or sheet.url
    try:
        created = datetime.fromisoformat(sheet.createdAt.replace("Z", "+00:00"))
        date_str = created.strftime("%d/%m/%Y")
    except Exception:
        date_str = ""
    out: list[Flowable] = [
        Spacer(1, 60 * mm),
        Paragraph("FICHE PROSPECT", styles["eyebrow"]),
        AccentBand(70, 4),
        Spacer(1, 14),
        Paragraph("Brief de prospection commerciale", styles["cover_kicker"]),
        Paragraph(_esc(name, limit=120), styles["cover_name"]),
        Spacer(1, 4),
        Paragraph(_esc(sheet.url, limit=200), styles["cover_meta"]),
        Spacer(1, 18),
    ]
    if ident and (ident.sector or ident.location):
        bits = " · ".join(b for b in [ident.sector, ident.location] if (b or "").strip())
        out.append(Paragraph(_esc(bits, limit=200), styles["body_sec"]))
        out.append(Spacer(1, 6))
    if date_str:
        out.append(Paragraph(f"Généré le {date_str}", styles["cover_date"]))
    out.append(PageBreak())
    return out


def _section_header(num: str, title: str, styles: dict) -> list[Flowable]:
    return [
        Paragraph(num, styles["section_num"]),
        Paragraph(_esc(title), styles["section_title"]),
        AccentBand(CONTENT_WIDTH, 1.5, BORDER_STRONG),
        Spacer(1, 10),
    ]


def _identity_section(sheet: ProspectSheet, styles: dict) -> list[Flowable]:
    out: list[Flowable] = _section_header("01", "Identité entreprise", styles)
    ident = sheet.identity
    if ident is None:
        out.append(Paragraph("Aucune information d'identité disponible.", styles["empty"]))
        return out
    inner: list[Flowable] = []
    kv = _kv_table([
        ("Raison sociale / nom", ident.name),
        ("Localisation", ident.location),
        ("Secteur", ident.sector),
        ("Année de création (estim.)", str(ident.estimatedFoundedYear) if ident.estimatedFoundedYear else ""),
        ("Taille estimée", ident.estimatedSize),
        ("Proposition de valeur", ident.valueProposition),
        ("Présence en ligne", ident.onlinePresenceNotes),
    ], styles)
    if kv is not None:
        inner.append(kv)
    if ident.socialProfiles:
        inner.append(Spacer(1, 6))
        inner.append(Paragraph("RÉSEAUX SOCIAUX", styles["label"]))
        for u in ident.socialProfiles[:12]:
            if (u or "").strip():
                inner.append(Paragraph(_esc(u, limit=160), styles["mono_sec"]))
    if not inner:
        inner.append(Paragraph("Aucune information d'identité disponible.", styles["empty"]))
    out.append(_card(inner))

    # Parent company / group
    pc = ident.parentCompany
    if pc is not None and (pc.name or "").strip():
        out.append(Spacer(1, 14))
        out.append(Paragraph("Groupe / maison-mère", styles["sub_title"]))
        out.append(_parent_company_card(pc, styles))
    return out


def _parent_company_card(pc: ProspectParentCompany, styles: dict) -> Table:
    inner: list[Flowable] = []
    kv = _kv_table([
        ("Groupe / société mère", pc.name),
        ("Nature du lien", pc.relation),
        ("Site", pc.website),
        ("Localisation", pc.location),
        ("Notes", pc.notes),
    ], styles)
    if kv is not None:
        inner.append(kv)
    sl = _source_line(pc.source, pc.sourceUrl, pc.sourceUrlOk, styles)
    if sl is not None:
        inner.append(Spacer(1, 4))
        inner.append(sl)
    if pc.contacts:
        inner.append(Spacer(1, 8))
        inner.append(Paragraph("CONTACTS DU GROUPE", styles["label"]))
        inner.append(Spacer(1, 4))
        for c in pc.contacts:
            full = " ".join(b for b in [c.firstName, c.lastName] if (b or "").strip()) or "—"
            line = f"<b>{_esc(full, limit=120)}</b>"
            if (c.role or "").strip():
                line += f" — {_esc(c.role, limit=160)}"
            inner.append(Paragraph(line, styles["body"]))
            sl2 = _source_line(c.source, c.sourceUrl, c.sourceUrlOk, styles)
            if sl2 is not None:
                inner.append(sl2)
            inner.append(Spacer(1, 4))
    return _card(inner)


def _stack_section(sheet: ProspectSheet, styles: dict) -> list[Flowable]:
    out: list[Flowable] = _section_header("02", "Stack technique détecté", styles)
    stack = sheet.stack
    cats = [
        ("cms", "CMS / plateforme"),
        ("analytics", "Analytics"),
        ("advertising", "Tags publicitaires"),
        ("chatCrm", "Chat / CRM"),
        ("hostingCdn", "Hébergeur / CDN"),
        ("other", "Autre"),
    ]
    any_tech = False
    inner: list[Flowable] = []
    if stack is not None:
        for attr, label in cats:
            items: list[DetectedTech] = getattr(stack, attr, []) or []
            if not items:
                continue
            any_tech = True
            inner.append(Paragraph(_esc(label).upper(), styles["label"]))
            inner.append(Spacer(1, 3))
            badges = [_tech_badge(t, styles) for t in items[:12]]
            # lay badges out 3 per row
            rows: list[list] = []
            for i in range(0, len(badges), 3):
                row = badges[i:i + 3]
                while len(row) < 3:
                    row.append("")
                rows.append(row)
            tbl = Table(rows, colWidths=[(CONTENT_WIDTH - 24) / 3] * 3)
            tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            inner.append(tbl)
            # evidence notes (compact)
            ev = [t.evidence for t in items if (t.evidence or "").strip()]
            for e in ev[:6]:
                inner.append(Paragraph(_esc(e, limit=200), styles["mono_sec"]))
            inner.append(Spacer(1, 6))
    if not any_tech:
        inner = [Paragraph("Aucune technologie identifiée automatiquement.", styles["empty"])]
    out.append(_card(inner))
    return out


def _contact_card(c: ProspectContact, styles: dict) -> Table:
    full = " ".join(b for b in [c.firstName, c.lastName] if (b or "").strip()) or "Personne identifiée"
    left: list[Flowable] = [Paragraph(_esc(full, limit=120), styles["name"])]
    if (c.role or "").strip():
        left.append(Paragraph(_esc(c.role, limit=200), styles["role"]))
    coord_rows: list[tuple[str, str]] = []
    if (c.email or "").strip():
        coord_rows.append(("Email", c.email))
    if (c.phone or "").strip():
        coord_rows.append(("Téléphone", c.phone))
    if (c.linkedin or "").strip():
        coord_rows.append(("LinkedIn", c.linkedin))
    if coord_rows:
        left.append(Spacer(1, 4))
        kv = _kv_table(coord_rows, styles)
        if kv is not None:
            left.append(kv)
    sl = _source_line(c.source, c.sourceUrl, c.sourceUrlOk, styles)
    if sl is not None:
        left.append(Spacer(1, 4))
        left.append(sl)
    right = [_confidence_badge(c.confidence, styles)]
    t = Table([[left, right]], colWidths=[CONTENT_WIDTH - 70 - 24, 70])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_ELEVATED),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (0, 0), "TOP"),
        ("VALIGN", (1, 0), (1, 0), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    return t


def _persona_section(sheet: ProspectSheet, styles: dict) -> list[Flowable]:
    out: list[Flowable] = _section_header("03", "Persona décideur, contacts & angles d'approche", styles)
    persona = sheet.persona
    if persona is None:
        out.append(Paragraph("Aucune information persona disponible.", styles["empty"]))
        return out

    # Named people
    out.append(Paragraph("Personnes identifiées", styles["sub_title"]))
    if persona.contacts:
        for c in persona.contacts:
            out.append(KeepTogether([_contact_card(c, styles), Spacer(1, 6)]))
    else:
        out.append(Paragraph("Aucune personne identifiée de façon fiable.", styles["empty"]))

    # Company-level coordinates
    rows: list[tuple[str, str]] = []
    if persona.companyEmails:
        rows.append(("Emails entreprise", " · ".join(persona.companyEmails[:10])))
    if persona.companyPhones:
        rows.append(("Téléphones entreprise", " · ".join(persona.companyPhones[:10])))
    if (persona.companyAddress or "").strip():
        rows.append(("Adresse du siège", persona.companyAddress))
    if rows:
        out.append(Spacer(1, 10))
        out.append(Paragraph("Coordonnées générales de l'entreprise", styles["sub_title"]))
        kv = _kv_table(rows, styles)
        if kv is not None:
            out.append(_card([kv]))

    # Roles to contact
    if persona.likelyContactRoles:
        out.append(Spacer(1, 10))
        out.append(Paragraph("Rôle·s probable·s à contacter", styles["sub_title"]))
        out.append(_card(_bullets(persona.likelyContactRoles, styles)))

    # Priorities / pains
    if persona.likelyPriorities:
        out.append(Spacer(1, 10))
        out.append(Paragraph("Priorités / douleurs probables", styles["sub_title"]))
        out.append(_card(_bullets(persona.likelyPriorities, styles)))

    # Approach angles
    if persona.approachAngles:
        out.append(Spacer(1, 10))
        out.append(Paragraph("Accroches de prospection", styles["sub_title"]))
        out.append(_card(_bullets(persona.approachAngles, styles)))

    return out


# ---------------------------------------------------------------------------
# Doc template + footer


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(FONT_MONO, 7.5)
    canvas.setFillColor(TEXT_TERTIARY)
    label = getattr(doc, "_footer_label", "Fiche prospect")
    canvas.drawString(LEFT_M, 10 * mm, label)
    canvas.drawRightString(PAGE_W - RIGHT_M, 10 * mm, f"{doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(LEFT_M, 13 * mm, PAGE_W - RIGHT_M, 13 * mm)
    canvas.restoreState()


def _make_doc(buffer: io.BytesIO, sheet: ProspectSheet) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        buffer, pagesize=A4,
        leftMargin=LEFT_M, rightMargin=RIGHT_M, topMargin=TOP_M, bottomMargin=BOTTOM_M,
        title=f"Fiche prospect — {(sheet.identity.name if sheet.identity else '') or sheet.domain}",
        author="Audit Bureau",
    )
    name = (sheet.identity.name if sheet.identity else "") or sheet.domain or "prospect"
    doc._footer_label = f"Fiche prospect · {name}"[:90]  # type: ignore[attr-defined]
    frame = Frame(LEFT_M, BOTTOM_M, CONTENT_WIDTH, PAGE_H - TOP_M - BOTTOM_M, id="main")
    cover_frame = Frame(LEFT_M, BOTTOM_M, CONTENT_WIDTH, PAGE_H - TOP_M - BOTTOM_M, id="cover")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame]),
        PageTemplate(id="body", frames=[frame], onPage=_footer),
    ])
    return doc


# ---------------------------------------------------------------------------
# Public API


def generate_prospect_pdf(sheet: ProspectSheet) -> bytes:
    """Render a prospect sheet as a polished PDF (bytes)."""
    buffer = io.BytesIO()
    doc = _make_doc(buffer, sheet)
    styles = _styles()
    story: list[Flowable] = [NextPageTemplate("body")]
    story += _cover(sheet, styles)  # ends with a PageBreak → next page = "body"
    story += _identity_section(sheet, styles)
    story.append(Spacer(1, 18))
    story += _stack_section(sheet, styles)
    story.append(PageBreak())
    story += _persona_section(sheet, styles)
    doc.build(story)
    return buffer.getvalue()


def write_prospect_pdf(sheet: ProspectSheet, path: str) -> str:
    data = generate_prospect_pdf(sheet)
    with open(path, "wb") as f:
        f.write(data)
    return path
