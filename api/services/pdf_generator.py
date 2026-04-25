"""Generate audit PDF reports with ReportLab.

Palette & typography follow docs/DESIGN.md (section PDF).
Structure: cover -> scores summary -> 6 sections -> SEO page sheets -> missing pages.

Layout guarantees:
- All widths derive from CONTENT_WIDTH (doc.width at A4 with 22mm margins).
- No inline <font size=...> that disrupts leading; every size change lives in its style.
- Cover score is drawn on canvas directly, not as a 72pt Paragraph.
"""

from __future__ import annotations

import html
import io
import os
from pathlib import Path
from typing import Optional


_MAX_TITLE = 300
_MAX_DESCRIPTION = 1200
_MAX_ACTION = 400
_MAX_EVIDENCE = 1500


def _esc(s: Optional[str], *, limit: Optional[int] = None) -> str:
    """Escape user/LLM-provided text for ReportLab's minimal HTML parser.

    Long strings are truncated so a pathological LLM output can't break
    the PDF's pagination (ReportLab can't split a single Paragraph across
    multiple pages).
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if limit is not None and len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return html.escape(s, quote=False)

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
    Image,
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
    AgencyBranding,
    AuditResult,
    Finding,
    MissingPage,
    PageAnalysis,
    PageRecommendation,
    SectionResult,
)
from api.services import branding as branding_service

# ---------------------------------------------------------------------------
# Page geometry

PAGE_W, PAGE_H = A4
LEFT_M = 22 * mm
RIGHT_M = 22 * mm
TOP_M = 22 * mm
BOTTOM_M = 18 * mm
CONTENT_WIDTH = PAGE_W - LEFT_M - RIGHT_M   # ~ 166 mm ~ 470 pt

# ---------------------------------------------------------------------------
# Palette (DESIGN.md §3 version claire, §7 cover)

BG_PAGE = colors.HexColor("#F7F5F0")
BG_SURFACE = colors.HexColor("#EDEAE3")
BG_ELEVATED = colors.HexColor("#FFFFFF")
TEXT_PRIMARY = colors.HexColor("#1A1A17")
TEXT_SECONDARY = colors.HexColor("#6B6860")
TEXT_TERTIARY = colors.HexColor("#9E9B94")
ACCENT = colors.HexColor("#B8892D")
BORDER = colors.HexColor("#D9D4C8")
BORDER_STRONG = colors.HexColor("#BFB9A8")

STATUS_COLORS: dict[str, tuple[colors.Color, colors.Color]] = {
    # (text, bg)
    "critical": (colors.HexColor("#DC2626"), colors.HexColor("#FEF2F2")),
    "warning": (colors.HexColor("#D97706"), colors.HexColor("#FFFBEB")),
    "ok": (colors.HexColor("#059669"), colors.HexColor("#F0FDF4")),
    "info": (colors.HexColor("#2563EB"), colors.HexColor("#EFF6FF")),
    "missing": (colors.HexColor("#7C3AED"), colors.HexColor("#F5F3FF")),
    "improve": (colors.HexColor("#D97706"), colors.HexColor("#FFFBEB")),
    "high": (colors.HexColor("#DC2626"), colors.HexColor("#FEF2F2")),
    "medium": (colors.HexColor("#D97706"), colors.HexColor("#FFFBEB")),
    "low": (colors.HexColor("#2563EB"), colors.HexColor("#EFF6FF")),
}

SEVERITY_LABEL = {
    "critical": "CRITIQUE",
    "warning": "ATTENTION",
    "ok": "OK",
    "info": "INFO",
    "missing": "MANQUANT",
}

PAGE_STATUS_LABEL = {
    "critical": "CRITIQUE",
    "warning": "ATTENTION",
    "improve": "À AMÉLIORER",
    "ok": "OK",
}

IMPACT_LABEL = {"high": "Impact fort", "medium": "Impact moyen", "low": "Impact faible"}
EFFORT_LABEL = {"quick": "Quick win", "medium": "Effort moyen", "heavy": "Chantier"}

# ---------------------------------------------------------------------------
# Fonts

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
    fonts_dir = Path(os.getenv("PDF_FONTS_DIR", Path(__file__).resolve().parents[1] / "fonts"))
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
# Styles


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "eyebrow": ParagraphStyle("eyebrow", parent=base, fontName=FONT_MONO_BD, fontSize=9,
                                  textColor=ACCENT, leading=11, spaceAfter=4),
        "cover_kicker": ParagraphStyle("cover_kicker", parent=base, fontName=FONT_DISPLAY_IT, fontSize=13,
                                       textColor=TEXT_SECONDARY, leading=16, spaceAfter=18),
        "cover_domain": ParagraphStyle("cover_domain", parent=base, fontName=FONT_DISPLAY, fontSize=32,
                                       textColor=TEXT_PRIMARY, leading=38, spaceAfter=4),
        "cover_url": ParagraphStyle("cover_url", parent=base, fontName=FONT_MONO, fontSize=10,
                                    textColor=TEXT_SECONDARY, leading=13, spaceAfter=2),
        "cover_date": ParagraphStyle("cover_date", parent=base, fontName=FONT_SANS, fontSize=11,
                                     textColor=TEXT_SECONDARY, leading=14, spaceAfter=4),
        "score_denom_label": ParagraphStyle("score_denom_label", parent=base, fontName=FONT_SANS,
                                            fontSize=11, textColor=TEXT_TERTIARY, leading=14),
        "score_verdict": ParagraphStyle("score_verdict", parent=base, fontName=FONT_DISPLAY_IT,
                                        fontSize=16, textColor=TEXT_PRIMARY, leading=20),
        "section_num": ParagraphStyle("section_num", parent=base, fontName=FONT_MONO_BD, fontSize=10,
                                      textColor=ACCENT, leading=12, spaceAfter=2),
        "section_title": ParagraphStyle("section_title", parent=base, fontName=FONT_DISPLAY, fontSize=24,
                                        textColor=TEXT_PRIMARY, leading=28, spaceAfter=4),
        "section_verdict": ParagraphStyle("section_verdict", parent=base, fontName=FONT_DISPLAY_IT,
                                          fontSize=12, textColor=TEXT_SECONDARY, leading=16,
                                          spaceAfter=14),
        "section_score_big": ParagraphStyle("section_score_big", parent=base, fontName=FONT_DISPLAY,
                                            fontSize=34, textColor=TEXT_PRIMARY, leading=38),
        "card_title": ParagraphStyle("card_title", parent=base, fontName=FONT_SANS_BD, fontSize=11,
                                     textColor=TEXT_PRIMARY, leading=15, spaceAfter=2),
        "body": ParagraphStyle("body", parent=base, fontName=FONT_SANS, fontSize=10,
                               textColor=TEXT_PRIMARY, leading=14),
        "body_sec": ParagraphStyle("body_sec", parent=base, fontName=FONT_SANS, fontSize=9,
                                   textColor=TEXT_SECONDARY, leading=13),
        "mono": ParagraphStyle("mono", parent=base, fontName=FONT_MONO, fontSize=9,
                               textColor=TEXT_PRIMARY, leading=12),
        "mono_sec": ParagraphStyle("mono_sec", parent=base, fontName=FONT_MONO, fontSize=8.5,
                                   textColor=TEXT_SECONDARY, leading=12),
        "mono_label": ParagraphStyle("mono_label", parent=base, fontName=FONT_MONO_BD, fontSize=7.5,
                                     textColor=TEXT_TERTIARY, leading=10),
        "reco_label": ParagraphStyle("reco_label", parent=base, fontName=FONT_MONO_BD, fontSize=7.5,
                                     textColor=ACCENT, leading=10),
        "evidence": ParagraphStyle("evidence", parent=base, fontName=FONT_MONO, fontSize=8.5,
                                   textColor=TEXT_SECONDARY, leading=12, leftIndent=8,
                                   borderPadding=0),
        "action_item": ParagraphStyle("action_item", parent=base, fontName=FONT_SANS, fontSize=9.5,
                                      textColor=TEXT_PRIMARY, leading=13, leftIndent=12,
                                      bulletIndent=0, spaceAfter=2),
        "quickwin_num": ParagraphStyle("quickwin_num", parent=base, fontName=FONT_MONO_BD, fontSize=10,
                                       textColor=ACCENT, leading=14),
    }


# ---------------------------------------------------------------------------
# Primitive flowables


def _score_color(score: int) -> colors.Color:
    if score < 40:
        return STATUS_COLORS["critical"][0]
    if score < 60:
        return STATUS_COLORS["warning"][0]
    if score < 80:
        return STATUS_COLORS["info"][0]
    return STATUS_COLORS["ok"][0]


class ScoreBar(Flowable):
    def __init__(self, score: int, width: float = 140, height: float = 6) -> None:
        super().__init__()
        self.score = max(0, min(100, score))
        self.w = width
        self.h = height

    def wrap(self, _aw: float, _ah: float) -> tuple[float, float]:
        return self.w, self.h

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(BG_SURFACE)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.3)
        c.rect(0, 0, self.w, self.h, stroke=1, fill=1)
        c.setFillColor(_score_color(self.score))
        c.rect(0, 0, self.w * (self.score / 100.0), self.h, stroke=0, fill=1)


class AccentBand(Flowable):
    def __init__(self, width: float, height: float = 5, color: colors.Color = ACCENT) -> None:
        super().__init__()
        self.w = width
        self.h = height
        self.color = color

    def wrap(self, _aw: float, _ah: float) -> tuple[float, float]:
        return self.w, self.h

    def draw(self) -> None:
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, self.w, self.h, stroke=0, fill=1)


class HRule(Flowable):
    def __init__(self, width: float, color: colors.Color = BORDER, thickness: float = 0.3) -> None:
        super().__init__()
        self.w = width
        self.color = color
        self.t = thickness

    def wrap(self, _aw: float, _ah: float) -> tuple[float, float]:
        return self.w, self.t

    def draw(self) -> None:
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.t)
        self.canv.line(0, 0, self.w, 0)


class ScoreHero(Flowable):
    """Draws the big cover score using canvas directly, so nothing overlaps."""

    def __init__(self, score: int, size: float = 78) -> None:
        super().__init__()
        self.score = max(0, min(100, score))
        self.size = size
        # leave room for the "/100" suffix on the right
        self._num_width = size * 1.25
        self._suffix_width = 40
        self.w = self._num_width + self._suffix_width
        self.h = size

    def wrap(self, _aw: float, _ah: float) -> tuple[float, float]:
        return self.w, self.h

    def draw(self) -> None:
        c = self.canv
        col = _score_color(self.score)
        c.setFillColor(col)
        c.setFont(FONT_DISPLAY, self.size)
        baseline = self.h * 0.18
        c.drawString(0, baseline, str(self.score))
        # /100 suffix
        c.setFillColor(TEXT_TERTIARY)
        c.setFont(FONT_SANS, 14)
        c.drawString(self._num_width - 6, baseline + self.size * 0.55, "/100")


# ---------------------------------------------------------------------------
# Components


def _badge(text: str, kind: str) -> Table:
    fg, bg = STATUS_COLORS.get(kind, (TEXT_PRIMARY, BG_SURFACE))
    cell = Paragraph(
        _esc(text),
        ParagraphStyle("badge_cell", fontName=FONT_MONO_BD, fontSize=7.5, textColor=fg, leading=9,
                       alignment=1),
    )
    # width = fixed-ish, avoid char-based heuristic that overflowed
    width = max(42, len(text) * 5 + 10)
    t = Table([[cell]], colWidths=[width], rowHeights=[13])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.4, fg),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    return t


def _counter_chip(count: int, label: str, kind: str, width: float = 220) -> Table:
    fg, bg = STATUS_COLORS[kind]
    count_para = Paragraph(
        str(count),
        ParagraphStyle("chip_count", fontName=FONT_DISPLAY, fontSize=26, textColor=fg, leading=28),
    )
    label_para = Paragraph(
        _esc(label),
        ParagraphStyle("chip_label", fontName=FONT_SANS, fontSize=10, textColor=TEXT_SECONDARY,
                       leading=13),
    )
    t = Table([[count_para, label_para]], colWidths=[40, width - 40])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LINEBEFORE", (0, 0), (0, -1), 2, fg),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 12),
                ("LEFTPADDING", (1, 0), (1, 0), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


# ---------------------------------------------------------------------------
# Cover


def _cover(
    audit: AuditResult,
    branding: AgencyBranding,
    accent_color: colors.Color,
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    date_str = audit.createdAt[:10]
    band_width = 80 * mm
    rule_width = 70 * mm

    flowables: list[Flowable] = [
        AccentBand(band_width, height=5, color=accent_color),
        Spacer(1, 24),
    ]

    logo_flow = _cover_logo(branding)
    if logo_flow is not None:
        flowables.append(logo_flow)
        flowables.append(Spacer(1, 16))

    flowables.extend([
        Paragraph("AUDIT WEB", styles["eyebrow"]),
        Paragraph("Rapport d'analyse SEO &amp; UX", styles["cover_kicker"]),
        HRule(rule_width),
        Spacer(1, 22),
        Paragraph(_esc(audit.domain), styles["cover_domain"]),
        Paragraph(_esc(audit.url), styles["cover_url"]),
        Spacer(1, 10),
        Paragraph(_esc(date_str), styles["cover_date"]),
        Spacer(1, 6),
        HRule(rule_width),
        Spacer(1, 28),
        ScoreHero(audit.globalScore, size=84),
        Spacer(1, 6),
        Paragraph("Score global", styles["score_denom_label"]),
        Spacer(1, 10),
        Paragraph(_esc(audit.globalVerdict), styles["score_verdict"]),
        Spacer(1, 34),
        _counter_chip(audit.criticalCount, "points critiques", "critical"),
        Spacer(1, 10),
        _counter_chip(audit.warningCount, "avertissements", "warning"),
        Spacer(1, 40),
        HRule(rule_width),
        Spacer(1, 10),
    ])

    # Footer line: agency name + tagline + website (when provided).
    footer_parts: list[str] = []
    if branding.name:
        footer_parts.append(f"Produit par {_esc(branding.name)}")
    if branding.tagline:
        footer_parts.append(_esc(branding.tagline))
    if branding.website:
        footer_parts.append(_esc(branding.website))
    footer_text = " · ".join(footer_parts) if footer_parts else "Rapport généré automatiquement"
    flowables.append(Paragraph(footer_text, styles["body_sec"]))
    flowables.append(PageBreak())
    return flowables


def _cover_logo(branding: AgencyBranding) -> Optional[Flowable]:
    """Return a `Image` flowable for the stored logo, or `None` if unavailable.

    We deliberately ignore SVG here — ReportLab doesn't render SVG natively and
    a silently broken logo is worse than none. SVG still ships in the PDF page
    header via `drawString` text fallback (name only).
    """
    try:
        path = branding_service.logo_path()
    except Exception:
        return None
    if path is None:
        return None
    if path.suffix.lower() == ".svg":
        return None  # not supported by ReportLab Image flowable
    try:
        img = Image(str(path))
    except Exception:
        return None
    max_w = 42 * mm
    max_h = 16 * mm
    # Scale down preserving aspect ratio
    w = float(img.imageWidth)
    h = float(img.imageHeight)
    if w <= 0 or h <= 0:
        return None
    ratio = min(max_w / w, max_h / h, 1.0)
    img.drawWidth = w * ratio
    img.drawHeight = h * ratio
    img.hAlign = "LEFT"
    return img


# ---------------------------------------------------------------------------
# Scores summary (section 01)


def _scores_summary(audit: AuditResult, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    rows: list[list] = [
        [
            Paragraph("AXE", styles["mono_label"]),
            Paragraph("SCORE", styles["mono_label"]),
            Paragraph("PROGRESSION", styles["mono_label"]),
            Paragraph("VERDICT", styles["mono_label"]),
        ]
    ]
    for sec in audit.sections:
        score_para = Paragraph(
            str(sec.score),
            ParagraphStyle("row_score", fontName=FONT_DISPLAY, fontSize=18,
                           textColor=_score_color(sec.score), leading=22),
        )
        rows.append(
            [
                Paragraph(_esc(sec.title, limit=_MAX_TITLE), styles["body"]),
                score_para,
                ScoreBar(sec.score, width=120, height=6),
                Paragraph(_esc(sec.verdict, limit=_MAX_DESCRIPTION), styles["body_sec"]),
            ]
        )

    col_axe = 90
    col_score = 45
    col_bar = 135
    col_verdict = CONTENT_WIDTH - (col_axe + col_score + col_bar)
    table = Table(rows, colWidths=[col_axe, col_score, col_bar, col_verdict])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, BORDER_STRONG),
                ("LINEBELOW", (0, 1), (-1, -2), 0.3, BORDER),
            ]
        )
    )

    return [
        Paragraph("01", styles["section_num"]),
        Paragraph("Vue d'ensemble", styles["section_title"]),
        Paragraph("Scores par axe d'audit", styles["section_verdict"]),
        table,
        Spacer(1, 22),
        *_quickwins(audit.quickWins, styles),
        PageBreak(),
    ]


def _quickwins(wins: list[str], styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    if not wins:
        return []
    items: list[Flowable] = [
        Paragraph("Quick wins prioritaires", styles["card_title"]),
        Spacer(1, 6),
    ]
    for i, w in enumerate(wins, 1):
        row = Table(
            [[Paragraph(f"{i:02d}", styles["quickwin_num"]), Paragraph(_esc(w), styles["body"])]],
            colWidths=[28, CONTENT_WIDTH - 28],
        )
        row.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        items.append(row)
    return items


# ---------------------------------------------------------------------------
# Finding card (used in axis sections and inside page sheets)


def _meta_chips(f: Finding, styles: dict[str, ParagraphStyle]) -> Optional[Table]:
    chips: list = []
    if f.impact:
        chips.append(_badge(IMPACT_LABEL[f.impact].upper(), f.impact))
    if f.effort:
        chips.append(
            _badge(
                EFFORT_LABEL[f.effort].upper(),
                "ok" if f.effort == "quick" else "info" if f.effort == "medium" else "warning",
            )
        )
    if not chips:
        return None
    cols = len(chips)
    t = Table([chips], colWidths=[60] * cols)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return t


def _finding_card(f: Finding, styles: dict[str, ParagraphStyle], width: float = CONTENT_WIDTH) -> Flowable:
    fg, bg = STATUS_COLORS.get(f.severity, (TEXT_PRIMARY, BG_SURFACE))
    label = SEVERITY_LABEL.get(f.severity, f.severity.upper())

    # Inner column of flowables — single-column story, wraps cleanly.
    inner: list[Flowable] = []

    # Row 1: severity badge (+ optional impact/effort chips)
    header_cells: list = [_badge(label, f.severity)]
    chips = _meta_chips(f, styles)
    if chips is not None:
        header_cells.append(chips)
    else:
        header_cells.append(Paragraph("", styles["body"]))
    inner.append(
        Table(
            [header_cells],
            colWidths=[80, width - 80 - 28],  # 28 = left stripe + paddings
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            ),
        )
    )
    inner.append(Spacer(1, 6))
    inner.append(Paragraph(_esc(f.title, limit=_MAX_TITLE), styles["card_title"]))
    inner.append(Paragraph(_esc(f.description, limit=_MAX_DESCRIPTION), styles["body"]))

    if f.evidence:
        inner.append(Spacer(1, 4))
        inner.append(Paragraph("EXTRAIT CONSTATÉ", styles["mono_label"]))
        inner.append(Paragraph(_esc(f.evidence, limit=_MAX_EVIDENCE), styles["evidence"]))

    if f.recommendation:
        inner.append(Spacer(1, 6))
        inner.append(Paragraph("RECOMMANDATION", styles["reco_label"]))
        inner.append(Paragraph(_esc(f.recommendation, limit=_MAX_DESCRIPTION), styles["body"]))

    if f.actions:
        inner.append(Spacer(1, 4))
        inner.append(Paragraph("ACTIONS", styles["reco_label"]))
        for a in f.actions:
            inner.append(
                Paragraph(f"•&nbsp;&nbsp;{_esc(a, limit=_MAX_ACTION)}", styles["action_item"])
            )

    if f.reference:
        inner.append(Spacer(1, 4))
        inner.append(
            Paragraph(
                f'<font color="{TEXT_TERTIARY.hexval()}">Référence :</font> '
                f'<font name="{FONT_MONO}" size="8">{_esc(f.reference)}</font>',
                styles["body_sec"],
            )
        )

    wrapper = Table([[inner]], colWidths=[width])
    wrapper.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LINEBEFORE", (0, 0), (0, -1), 3, fg),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return KeepTogether([wrapper, Spacer(1, 8)])


# ---------------------------------------------------------------------------
# Axis section


def _section_block(idx: int, sec: SectionResult, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    header_row = Table(
        [
            [
                Paragraph(str(sec.score), styles["section_score_big"]),
                ScoreBar(sec.score, width=CONTENT_WIDTH - 100, height=8),
            ]
        ],
        colWidths=[90, CONTENT_WIDTH - 90],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )

    block: list[Flowable] = [
        Paragraph(f"{idx:02d}", styles["section_num"]),
        Paragraph(_esc(sec.title, limit=_MAX_TITLE), styles["section_title"]),
        Paragraph(_esc(sec.verdict, limit=_MAX_DESCRIPTION), styles["section_verdict"]),
        header_row,
        Spacer(1, 18),
    ]
    if not sec.findings:
        block.append(Paragraph("Aucun point remonté sur cet axe.", styles["body_sec"]))
    for f in sec.findings:
        block.append(_finding_card(f, styles))
    block.append(PageBreak())
    return block


# ---------------------------------------------------------------------------
# Page sheet (SEO section)


def _kv_row(label: str, value_flowable: Flowable, right: Optional[Flowable], styles: dict[str, ParagraphStyle]) -> list:
    return [Paragraph(label, styles["mono_label"]), value_flowable, right or Paragraph("", styles["body"])]


def _page_sheet(page: PageAnalysis, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    """Render a page sheet as a flat sequence of flowables so pagination can split cleanly."""
    fg, _bg = STATUS_COLORS.get(page.status, (TEXT_PRIMARY, BG_SURFACE))
    label = PAGE_STATUS_LABEL.get(page.status, page.status.upper())

    # Colored banner with URL + status — KeepTogether only with its meta/kw tables,
    # never the whole sheet (findings + reco must be allowed to flow across pages).
    banner = Table(
        [[Paragraph(_esc(page.url), styles["mono_sec"]), _badge(label, page.status)]],
        colWidths=[CONTENT_WIDTH - 110, 100],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BACKGROUND", (0, 0), (-1, -1), BG_SURFACE),
                ("LINEBEFORE", (0, 0), (0, -1), 4, fg),
                ("LEFTPADDING", (0, 0), (0, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        ),
    )

    # Meta table: TITLE / H1 / META with lengths
    meta_rows = [
        _kv_row(
            "TITLE",
            Paragraph(_esc(page.title, limit=_MAX_TITLE) or "<i>absent</i>", styles["body"]),
            Paragraph(f"{page.titleLength} car.", styles["mono_sec"]),
            styles,
        ),
        _kv_row(
            "H1",
            Paragraph(_esc(page.h1, limit=_MAX_TITLE) or "<i>absent</i>", styles["body"]),
            None,
            styles,
        ),
        _kv_row(
            "META",
            Paragraph(
                _esc(page.metaDescription, limit=_MAX_DESCRIPTION) or "<i>absente</i>",
                styles["body"],
            ),
            Paragraph(f"{page.metaLength} car.", styles["mono_sec"]),
            styles,
        ),
    ]
    meta_table = Table(
        meta_rows,
        colWidths=[55, CONTENT_WIDTH - 55 - 55, 55],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        ),
    )

    def kw_row(label_: str, values: list[str], color: colors.Color = TEXT_PRIMARY) -> list:
        text = ", ".join(_esc(v) for v in values) if values else "—"
        return [
            Paragraph(label_, styles["mono_label"]),
            Paragraph(
                f'<font color="{color.hexval()}">{text}</font>',
                styles["body"],
            ),
        ]

    kw_table = Table(
        [
            kw_row("KW CIBLES", page.targetKeywords, ACCENT),
            kw_row("PRÉSENTS", page.presentKeywords, STATUS_COLORS["ok"][0]),
            kw_row("ABSENTS", page.missingKeywords, STATUS_COLORS["critical"][0]),
        ],
        colWidths=[75, CONTENT_WIDTH - 75],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        ),
    )

    blocks: list[Flowable] = [
        # Keep banner + meta + kw tables together — identity card of the page
        KeepTogether([banner, Spacer(1, 6), meta_table, Spacer(1, 2), kw_table]),
        Spacer(1, 10),
    ]

    # Findings — each card is allowed to break naturally between cards
    for f in page.findings:
        blocks.append(_finding_card(f, styles, width=CONTENT_WIDTH))

    # Recommendation block
    if page.recommendation:
        blocks.append(Spacer(1, 4))
        blocks.append(Paragraph("RECOMMANDATION DÉTAILLÉE", styles["reco_label"]))
        blocks.append(Spacer(1, 4))
        blocks.extend(_reco_table(page.recommendation, CONTENT_WIDTH, styles))

    blocks.append(Spacer(1, 14))
    blocks.append(HRule(CONTENT_WIDTH, color=BORDER_STRONG, thickness=0.6))
    blocks.append(Spacer(1, 14))
    return blocks


def _reco_table(r: PageRecommendation, width: float, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    """BEFORE / AFTER comparison for URL / Title / H1 / Meta + actions + traffic.

    Returns a list of flowables (not a single Table) so long action lists can
    paginate without hitting the unsplittable-cell LayoutError.
    """

    def row(label_: str, current: Optional[str], proposed: Optional[str], mono: bool = False) -> list:
        current_style = styles["mono"] if mono else styles["body"]
        proposed_style = styles["mono"] if mono else styles["body"]
        current_txt = _esc(current, limit=_MAX_DESCRIPTION) if current else "—"
        proposed_txt = _esc(proposed, limit=_MAX_DESCRIPTION) if proposed else "—"
        return [
            Paragraph(label_, styles["mono_label"]),
            Paragraph(current_txt, current_style),
            Paragraph(
                f'<font color="{ACCENT.hexval()}">{proposed_txt}</font>',
                proposed_style,
            ),
        ]

    header = [
        Paragraph("CHAMP", styles["mono_label"]),
        Paragraph("ACTUEL", styles["mono_label"]),
        Paragraph("RECOMMANDÉ", styles["reco_label"]),
    ]

    rows: list[list] = [header]
    if r.urlCurrent or r.url:
        rows.append(row("URL", r.urlCurrent, r.url, mono=True))
    if r.titleCurrent or r.title:
        rows.append(row("TITLE", r.titleCurrent, r.title))
    if r.h1Current or r.h1:
        rows.append(row("H1", r.h1Current, r.h1))
    if r.metaCurrent or r.meta:
        rows.append(row("META", r.metaCurrent, r.meta))

    col_label = 55
    col_current = (width - col_label) / 2
    col_prop = width - col_label - col_current
    table = Table(rows, colWidths=[col_label, col_current, col_prop])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), BG_SURFACE),
                ("LINEABOVE", (0, 0), (-1, 0), 0.4, BORDER),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
                ("LINEAFTER", (1, 0), (1, -1), 0.3, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    out_blocks: list[Flowable] = [table]
    if r.actions:
        out_blocks.append(Spacer(1, 8))
        out_blocks.append(Paragraph("ACTIONS TECHNIQUES", styles["reco_label"]))
        for a in r.actions:
            out_blocks.append(
            Paragraph(
                f"•&nbsp;&nbsp;{_esc(a, limit=_MAX_ACTION)}",
                styles["action_item"],
            )
        )
    if r.estimatedMonthlyTraffic:
        out_blocks.append(Spacer(1, 6))
        out_blocks.append(
            Paragraph(
                f'<font color="{TEXT_TERTIARY.hexval()}">Trafic mensuel estimé :</font> '
                f'<font color="{ACCENT.hexval()}">~{r.estimatedMonthlyTraffic} visites/mois</font>',
                styles["body_sec"],
            )
        )
    return out_blocks


def _pages_section(pages: list[PageAnalysis], styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    out: list[Flowable] = [
        Paragraph("08", styles["section_num"]),
        Paragraph("Analyse page par page", styles["section_title"]),
        Paragraph(
            _esc(f"{len(pages)} pages analysées — état actuel, diagnostic et recommandations détaillées"),
            styles["section_verdict"],
        ),
    ]
    for p in pages:
        out.extend(_page_sheet(p, styles))
    out.append(PageBreak())
    return out


def _missing_pages_section(missing: list[MissingPage], styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    header = [
        Paragraph("URL RECOMMANDÉE", styles["mono_label"]),
        Paragraph("RAISON", styles["mono_label"]),
        Paragraph("VOL./MOIS", styles["mono_label"]),
        Paragraph("PRIORITÉ", styles["mono_label"]),
    ]
    rows: list[list] = [header]
    for m in missing:
        priority_kind = {"high": "critical", "medium": "warning", "low": "info"}.get(m.priority, "info")
        rows.append(
            [
                Paragraph(_esc(m.url, limit=_MAX_TITLE), styles["mono"]),
                Paragraph(_esc(m.reason, limit=_MAX_DESCRIPTION), styles["body"]),
                Paragraph(
                    f"~{m.estimatedSearchVolume}" if m.estimatedSearchVolume else "—",
                    styles["mono"],
                ),
                _badge(m.priority.upper(), priority_kind),
            ]
        )

    col_url = 150
    col_vol = 55
    col_prio = 60
    col_reason = CONTENT_WIDTH - (col_url + col_vol + col_prio)
    table = Table(rows, colWidths=[col_url, col_reason, col_vol, col_prio])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), BG_SURFACE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, BORDER_STRONG),
            ]
        )
    )
    return [
        Paragraph("09", styles["section_num"]),
        Paragraph("Pages stratégiques manquantes", styles["section_title"]),
        Paragraph(
            _esc(f"{len(missing)} pages à créer pour combler les gaps SEO détectés"),
            styles["section_verdict"],
        ),
        table,
    ]


# ---------------------------------------------------------------------------
# Document template


def _make_doc(
    buffer: io.BytesIO, audit: AuditResult, branding: AgencyBranding,
) -> BaseDocTemplate:
    author = branding.name or "Audit Web IA"
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=LEFT_M,
        rightMargin=RIGHT_M,
        topMargin=TOP_M,
        bottomMargin=BOTTOM_M,
        title=f"Audit {audit.domain}",
        author=author,
    )

    frame_cover = Frame(LEFT_M, BOTTOM_M, doc.width, doc.height, id="cover", showBoundary=0)
    frame_body = Frame(
        LEFT_M, BOTTOM_M, doc.width, doc.height - 12 * mm, id="body", showBoundary=0,
        topPadding=0,
    )

    footer_right = (branding.name or "AUDIT WEB IA")[:60].upper()

    def _paint_bg(canvas, _doc) -> None:
        canvas.saveState()
        canvas.setFillColor(BG_PAGE)
        canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canvas.restoreState()

    def _paint_header_footer(canvas, _doc) -> None:
        _paint_bg(canvas, _doc)
        canvas.saveState()
        # Header
        canvas.setFont(FONT_MONO, 8)
        canvas.setFillColor(TEXT_TERTIARY)
        canvas.drawString(LEFT_M, PAGE_H - 14 * mm, audit.domain)
        canvas.drawRightString(PAGE_W - RIGHT_M, PAGE_H - 14 * mm, f"Page {_doc.page}")
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.3)
        canvas.line(LEFT_M, PAGE_H - 16 * mm, PAGE_W - RIGHT_M, PAGE_H - 16 * mm)
        # Footer
        canvas.setFont(FONT_MONO, 7)
        canvas.setFillColor(TEXT_TERTIARY)
        canvas.drawString(LEFT_M, 12 * mm, audit.createdAt[:10])
        canvas.drawRightString(PAGE_W - RIGHT_M, 12 * mm, footer_right)
        canvas.restoreState()

    doc.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[frame_cover], onPage=_paint_bg),
            PageTemplate(id="body", frames=[frame_body], onPage=_paint_header_footer),
        ]
    )
    return doc


# ---------------------------------------------------------------------------
# Public API


def generate_pdf(
    audit: AuditResult,
    agency_name: Optional[str] = None,
    *,
    branding: Optional[AgencyBranding] = None,
) -> bytes:
    """Render the audit as PDF.

    `branding` (optional): overrides `agency_name` and adds logo + accent
    colour. When absent the PDF falls back to the default palette and the
    `agency_name` argument (kept for backward-compat with the POST /audit/pdf
    endpoint).
    """
    if branding is None:
        branding = AgencyBranding(name=agency_name)
    elif agency_name and not branding.name:
        branding = branding.model_copy(update={"name": agency_name})

    accent = _resolve_accent(branding.accentColor)

    buffer = io.BytesIO()
    doc = _make_doc(buffer, audit, branding)
    styles = _styles()

    story: list[Flowable] = []
    story += _cover(audit, branding, accent, styles)
    story += [NextPageTemplate("body")]
    story += _scores_summary(audit, styles)

    for i, sec in enumerate(audit.sections, 1):
        story += _section_block(i + 1, sec, styles)

    if audit.pages:
        story += _pages_section(audit.pages, styles)

    if audit.missingPages:
        story += _missing_pages_section(audit.missingPages, styles)

    doc.build(story)
    return buffer.getvalue()


def _resolve_accent(hex_color: Optional[str]) -> colors.Color:
    """Custom accent colour → ReportLab Color, with fallback to house default."""
    if hex_color:
        try:
            return colors.HexColor(hex_color)
        except Exception:
            pass
    return ACCENT


def write_pdf(
    audit: AuditResult,
    path: str,
    agency_name: Optional[str] = None,
    *,
    branding: Optional[AgencyBranding] = None,
) -> str:
    data = generate_pdf(audit, agency_name, branding=branding)
    with open(path, "wb") as f:
        f.write(data)
    return path
