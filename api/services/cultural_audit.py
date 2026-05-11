"""Cultural adaptation audit for multilingual sites.

Beyond hreflang syntax: when a site serves a page in language X, do the
date / number / currency formats and the CTA wording actually match what
that audience expects? Mismatches (a /en-US page with DD/MM/YYYY dates
and EUR prices and French CTAs) erode trust and conversion.

Pure Python — regex + small per-language profiles. Original concept of
cultural profiles: Chris Muller (Pro Hub Challenge), via AgriciDaniel/claude-seo.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# --- Per-language expectations ---------------------------------------------

# expectedCurrencies: ISO codes / symbols that are normal for this language.
# foreignCurrencyHints: symbols whose presence on a page of this language is
#   a likely mismatch (we only flag the obvious cross-pairs).
# numberFormat: human label of the expected thousands/decimal separators.
# dateFormat: human label.
# ctaStopwords: words that, if they dominate the CTAs, signal wrong-language.
PROFILES: dict[str, dict] = {
    "fr": {
        "label": "Francophone",
        "expectedCurrencies": {"EUR", "€", "CHF", "CAD"},
        "numberFormat": "1 000,00 (espace milliers, virgule décimale)",
        "dateFormat": "JJ/MM/AAAA",
        "legalPages": ["mentions légales", "cgv", "politique de confidentialité"],
        "otherLangCtaWords": {"buy now", "get started", "sign up", "learn more", "shop now",
                              "jetzt kaufen", "mehr erfahren", "comprar ahora", "saperne di più"},
    },
    "de": {
        "label": "DACH (DE/AT/CH)",
        "expectedCurrencies": {"EUR", "€", "CHF"},
        "numberFormat": "1.000,00 (point milliers, virgule décimale)",
        "dateFormat": "TT.MM.JJJJ",
        "legalPages": ["impressum", "datenschutz", "agb", "widerrufsrecht"],
        "otherLangCtaWords": {"buy now", "get started", "sign up", "learn more", "shop now",
                              "acheter maintenant", "en savoir plus", "comprar ahora"},
    },
    "es": {
        "label": "Hispanophone (ES/LATAM)",
        "expectedCurrencies": {"EUR", "€", "MXN", "ARS", "COP", "CLP", "PEN"},
        "numberFormat": "1.000,00 (ES) / variable LATAM",
        "dateFormat": "DD/MM/AAAA",
        "legalPages": ["aviso legal", "política de privacidad", "términos y condiciones"],
        "otherLangCtaWords": {"buy now", "get started", "sign up", "learn more", "shop now",
                              "acheter maintenant", "jetzt kaufen", "saperne di più"},
    },
    "en": {
        "label": "Anglophone",
        "expectedCurrencies": {"USD", "$", "GBP", "£", "EUR", "€"},
        "numberFormat": "1,000.00 (comma thousands, dot decimal)",
        "dateFormat": "MM/DD/YYYY (US) ou DD/MM/YYYY (UK)",
        "legalPages": ["privacy policy", "terms", "terms of service", "terms and conditions"],
        "otherLangCtaWords": {"acheter maintenant", "en savoir plus", "jetzt kaufen",
                              "mehr erfahren", "comprar ahora", "saperne di più"},
    },
    "it": {
        "label": "Italophone",
        "expectedCurrencies": {"EUR", "€"},
        "numberFormat": "1.000,00 (point milliers, virgule décimale)",
        "dateFormat": "GG/MM/AAAA",
        "legalPages": ["note legali", "informativa sulla privacy", "termini e condizioni"],
        "otherLangCtaWords": {"buy now", "get started", "acheter maintenant", "jetzt kaufen",
                              "comprar ahora"},
    },
    "nl": {
        "label": "Néerlandophone",
        "expectedCurrencies": {"EUR", "€"},
        "numberFormat": "1.000,00 (point milliers, virgule décimale)",
        "dateFormat": "DD-MM-JJJJ",
        "legalPages": ["privacybeleid", "algemene voorwaarden"],
        "otherLangCtaWords": {"buy now", "acheter maintenant", "jetzt kaufen", "comprar ahora"},
    },
    "pt": {
        "label": "Lusophone",
        "expectedCurrencies": {"EUR", "€", "BRL", "R$"},
        "numberFormat": "1.000,00 (PT) / 1.000,00 (BR)",
        "dateFormat": "DD/MM/AAAA",
        "legalPages": ["política de privacidade", "termos e condições"],
        "otherLangCtaWords": {"buy now", "acheter maintenant", "jetzt kaufen", "comprar ahora"},
    },
}

# Currency symbols → ISO families (for "foreign currency" detection).
_CURRENCY_SYMBOLS = {
    "€": "EUR", "$": "USD", "£": "GBP", "¥": "JPY", "₩": "KRW",
    "R$": "BRL", "CHF": "CHF",
}

_DATE_DMY = re.compile(r"\b([0-3]?\d)[/.]([01]?\d)[/.](20\d{2})\b")
_DATE_MDY_US = re.compile(r"\b([01]?\d)/([0-3]?\d)/(20\d{2})\b")  # ambiguous, US-leaning
_NUMBER_DOT_THOUSANDS = re.compile(r"\b\d{1,3}(\.\d{3})+(,\d+)?\b")  # 1.000,00
_NUMBER_COMMA_THOUSANDS = re.compile(r"\b\d{1,3}(,\d{3})+(\.\d+)?\b")  # 1,000.00

_CTA_TAG_HINT = re.compile(r"(button|btn|cta|call-to-action)", re.I)


def _norm_lang(lang: str) -> str:
    """'fr-FR' / 'FR' / 'fr_ca' -> 'fr'."""
    if not lang:
        return ""
    return lang.strip().lower().replace("_", "-").split("-")[0]


def detect_page_locale(*, html_lang: str, hreflang_self: str, url: str) -> str:
    """Best guess of the locale a page is served in: html lang first, then a
    self hreflang, then URL path segment (/fr/, /de-de/)."""
    for src in (html_lang, hreflang_self):
        n = _norm_lang(src or "")
        if n in PROFILES:
            return n
    path_parts = [p for p in urlparse(url).path.split("/") if p]
    if path_parts:
        n = _norm_lang(path_parts[0])
        if n in PROFILES:
            return n
    return ""


def _extract_cta_texts(soup) -> list[str]:
    """Anchor/button texts that look like CTAs."""
    out: list[str] = []
    for tag in soup.find_all(["a", "button"]):
        cls = " ".join(tag.get("class") or [])
        role = tag.get("role") or ""
        if tag.name == "button" or _CTA_TAG_HINT.search(cls) or role == "button":
            txt = tag.get_text(" ", strip=True)
            if 2 < len(txt) < 40:
                out.append(txt)
    return out[:30]


def audit_page(
    *,
    locale: str,
    body_text: str,
    cta_texts: list[str],
) -> list[str]:
    """Return a list of human-readable cultural-mismatch findings for one page.
    `locale` must be a key of PROFILES; empty/unknown → no findings."""
    prof = PROFILES.get(locale)
    if not prof:
        return []
    issues: list[str] = []
    text = body_text or ""
    low = text.lower()

    # 1. Foreign currency symbols.
    found_syms = {sym for sym in _CURRENCY_SYMBOLS if sym in text}
    found_iso = {_CURRENCY_SYMBOLS[s] for s in found_syms}
    # also catch bare ISO codes
    for iso in ("USD", "EUR", "GBP", "JPY", "CHF", "BRL", "CAD"):
        if re.search(rf"\b{iso}\b", text):
            found_iso.add(iso)
    foreign = found_iso - prof["expectedCurrencies"]
    if foreign:
        issues.append(
            f"Devise(s) inhabituelle(s) pour une page {prof['label']} : "
            f"{', '.join(sorted(foreign))} — vérifier la cohérence des prix."
        )

    # 2. Number format mismatch (only flag the clear cross-case).
    has_dot_thousands = bool(_NUMBER_DOT_THOUSANDS.search(text))
    has_comma_thousands = bool(_NUMBER_COMMA_THOUSANDS.search(text))
    if locale in ("fr", "de", "es", "it", "nl", "pt") and has_comma_thousands and not has_dot_thousands:
        issues.append(
            f"Nombres au format anglo-saxon (1,000.00) sur une page {prof['label']} "
            f"— format attendu : {prof['numberFormat']}."
        )
    if locale == "en" and has_dot_thousands and not has_comma_thousands:
        issues.append(
            "Nombres au format européen (1.000,00) sur une page anglophone "
            "— format attendu : 1,000.00."
        )

    # 3. CTA language mismatch.
    bad_cta = []
    cta_lows = [c.lower() for c in cta_texts]
    for cta in cta_lows:
        for w in prof["otherLangCtaWords"]:
            if w in cta:
                bad_cta.append(cta)
                break
    if bad_cta:
        sample = ", ".join(f'"{c}"' for c in bad_cta[:4])
        issues.append(
            f"CTA dans une autre langue sur une page {prof['label']} : {sample}"
            + (" …" if len(bad_cta) > 4 else "")
        )

    # 4. Legal pages keyword presence (light heuristic on the body text).
    missing_legal = [p for p in prof["legalPages"] if p not in low]
    # Only worth flagging when NONE of them appear (page likely has no legal links).
    if len(missing_legal) == len(prof["legalPages"]):
        issues.append(
            f"Aucune mention des pages légales attendues ({', '.join(prof['legalPages'])}) "
            f"trouvée dans le contenu — vérifier la présence des liens légaux requis."
        )

    return issues
