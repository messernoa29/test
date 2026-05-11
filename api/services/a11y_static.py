"""Static accessibility & responsive signal extraction from a parsed page.

These checks need only the HTML (and any inline CSS), so they run inside the
crawler with no extra fetches. The deeper checks (real contrast, focus
visibility, tab order, horizontal scroll at width) require a browser and are
done elsewhere (Playwright pass) or by an LLM verdict.
"""

from __future__ import annotations

import re

# Link texts that convey no context out of place.
_GENERIC_LINK_RE = re.compile(
    r"^\s*(cliquez ici|cliquer ici|clic ici|en savoir plus|lire la suite|"
    r"voir plus|read more|learn more|click here|here|details?|détails?|"
    r"plus d['’]infos?|ici|link|lien)\s*$",
    re.I,
)
_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_VIEWPORT_BLOCK_ZOOM_RE = re.compile(
    r"(user-scalable\s*=\s*no|maximum-scale\s*=\s*1(\.0)?\b)", re.I
)
_MEDIA_QUERY_RE = re.compile(r"@media[^{]+\{", re.I)
_FONT_PX_RE = re.compile(r"font-size\s*:\s*(\d+)px", re.I)
_WIDTH_PX_RE = re.compile(r"(?<![-\w])width\s*:\s*(\d+)px", re.I)


def _has_label(node) -> bool:
    """A form control is considered labelled if it has aria-label /
    aria-labelledby / title, or a <label for=id> exists, or it's wrapped in a
    <label>."""
    if node.get("aria-label") or node.get("aria-labelledby") or node.get("title"):
        return True
    nid = node.get("id")
    if nid:
        # Look for a matching <label for=...> anywhere in the document.
        root = node
        while root.parent is not None:
            root = root.parent
        if root.find("label", attrs={"for": nid}) is not None:
            return True
    # Wrapped in a <label>?
    p = node.parent
    while p is not None:
        if getattr(p, "name", None) == "label":
            return True
        p = p.parent
    return False


def extract_a11y(soup) -> dict:
    """Return a dict matching PageA11y."""
    issues: list[str] = []

    html_tag = soup.find("html")
    html_has_lang = bool(html_tag and (html_tag.get("lang") or "").strip())
    if not html_has_lang:
        issues.append("attribut lang absent sur <html>")

    imgs = soup.find_all("img")
    imgs_total = len(imgs)
    imgs_no_alt = sum(1 for i in imgs if i.get("alt") is None)
    imgs_alt_empty = sum(1 for i in imgs if (i.get("alt") or "").strip() == "" and i.get("alt") is not None)
    if imgs_no_alt:
        issues.append(f"{imgs_no_alt} image(s) sans attribut alt")

    # Form controls (skip hidden / submit / button which often don't need a label).
    controls = []
    for tag in soup.find_all(["input", "select", "textarea"]):
        t = (tag.get("type") or "").lower()
        if tag.name == "input" and t in ("hidden", "submit", "button", "reset", "image"):
            continue
        controls.append(tag)
    inputs_total = len(controls)
    inputs_no_label = sum(1 for c in controls if not _has_label(c))
    if inputs_no_label:
        issues.append(f"{inputs_no_label} champ(s) de formulaire sans label")

    # Buttons faked with <div>/<span> + onclick and no role/keyboard support.
    buttons_as_div = 0
    for tag in soup.find_all(["div", "span"]):
        if tag.get("onclick") and tag.get("role") not in ("button", "link"):
            buttons_as_div += 1
        elif tag.get("role") == "button" and tag.get("tabindex") is None:
            buttons_as_div += 1
    if buttons_as_div:
        issues.append(f"{buttons_as_div} \"bouton(s)\" faits en <div>/<span> (pas accessibles au clavier)")

    # Links: empty and generic.
    links_empty = 0
    links_generic = 0
    for a in soup.find_all("a"):
        txt = a.get_text(" ", strip=True)
        if not txt and not a.get("aria-label") and not a.find("img", alt=True):
            links_empty += 1
        elif txt and _GENERIC_LINK_RE.match(txt):
            links_generic += 1
    if links_empty:
        issues.append(f"{links_empty} lien(s) sans texte ni aria-label")
    if links_generic:
        issues.append(f"{links_generic} lien(s) au texte non descriptif (« cliquez ici »…)")

    # Headings: count h1, detect skipped levels.
    headings = []
    for h in soup.find_all(_HEADING_TAGS):
        try:
            level = int(h.name[1])
            headings.append(level)
        except (ValueError, IndexError):
            pass
    h1_count = sum(1 for lv in headings if lv == 1)
    heading_order_issues = 0
    prev = 0
    for lv in headings:
        if prev and lv > prev + 1:
            heading_order_issues += 1
        prev = lv
    if h1_count == 0:
        issues.append("aucun <h1>")
    elif h1_count > 1:
        issues.append(f"{h1_count} <h1> sur la page (un seul recommandé)")
    if heading_order_issues:
        issues.append(f"{heading_order_issues} saut(s) de niveau de titre (ex. h1 → h3)")

    # Positive tabindex breaks the natural tab order.
    positive_tabindex = 0
    for tag in soup.find_all(attrs={"tabindex": True}):
        try:
            if int(tag.get("tabindex")) > 0:
                positive_tabindex += 1
        except (TypeError, ValueError):
            pass
    if positive_tabindex:
        issues.append(f"{positive_tabindex} élément(s) avec tabindex positif (casse l'ordre de tabulation)")

    # iframes without a title.
    iframe_no_title = sum(
        1 for f in soup.find_all("iframe")
        if not (f.get("title") or "").strip() and not f.get("aria-label")
    )
    if iframe_no_title:
        issues.append(f"{iframe_no_title} <iframe> sans titre")

    # Skip link near the top.
    skip_link = False
    for a in soup.find_all("a", href=True)[:5]:
        href = a.get("href", "")
        txt = a.get_text(" ", strip=True).lower()
        if href.startswith("#") and ("contenu" in txt or "content" in txt or "aller au" in txt or "skip" in txt):
            skip_link = True
            break

    # Landmarks.
    landmarks = bool(soup.find("main") or soup.find(attrs={"role": "main"}))
    if not landmarks:
        issues.append("pas de <main> / role=main (repère pour les lecteurs d'écran)")

    # Obviously broken aria-* values.
    aria_invalid = 0
    for tag in soup.find_all(True):
        v = tag.get("aria-hidden")
        if v is not None and str(v).lower() not in ("true", "false"):
            aria_invalid += 1
        v = tag.get("aria-expanded")
        if v is not None and str(v).lower() not in ("true", "false"):
            aria_invalid += 1

    return {
        "htmlHasLang": html_has_lang,
        "imagesTotal": imgs_total,
        "imagesWithoutAlt": imgs_no_alt,
        "imagesAltEmpty": imgs_alt_empty,
        "formInputsTotal": inputs_total,
        "formInputsWithoutLabel": inputs_no_label,
        "buttonsAsDiv": buttons_as_div,
        "linksEmpty": links_empty,
        "linksGeneric": links_generic,
        "h1Count": h1_count,
        "headingOrderIssues": heading_order_issues,
        "positiveTabindex": positive_tabindex,
        "iframeWithoutTitle": iframe_no_title,
        "skipLinkPresent": skip_link,
        "landmarksPresent": landmarks,
        "ariaInvalidCount": aria_invalid,
        "issues": issues,
    }


def extract_responsive(soup, html: str) -> dict:
    """Return a dict matching PageResponsive (static fields only)."""
    issues: list[str] = []

    vp = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    vp_content = (vp.get("content") if vp else "") or ""
    has_viewport = bool(vp)
    blocks_zoom = bool(_VIEWPORT_BLOCK_ZOOM_RE.search(vp_content))
    if not has_viewport:
        issues.append("<meta name=viewport> absent (page non responsive)")
    elif blocks_zoom:
        issues.append("le viewport empêche le zoom (user-scalable=no / maximum-scale=1)")

    # Count @media rules in inline <style> blocks + the raw HTML (linked CSS we
    # don't fetch, but many sites inline critical CSS).
    css_text = " ".join(s.get_text() for s in soup.find_all("style"))
    media_queries = len(_MEDIA_QUERY_RE.findall(css_text)) + len(_MEDIA_QUERY_RE.findall(html))

    imgs = soup.find_all("img")
    imgs_total = len(imgs)
    imgs_srcset = sum(1 for i in imgs if i.get("srcset") or i.get("data-srcset"))

    # Inline-style px fonts / large fixed widths (only what's in style="...").
    inline_styles = " ".join(t.get("style", "") for t in soup.find_all(style=True))
    fixed_px_fonts = sum(1 for m in _FONT_PX_RE.finditer(inline_styles) if int(m.group(1)) < 16)
    large_fixed_widths = sum(1 for m in _WIDTH_PX_RE.finditer(inline_styles) if int(m.group(1)) > 768)
    if not media_queries and has_viewport:
        issues.append("aucune media query détectée dans le CSS inline (mise en page peut-être non adaptative)")
    if large_fixed_widths:
        issues.append(f"{large_fixed_widths} largeur(s) fixe(s) > 768px en style inline (risque de scroll horizontal mobile)")
    if fixed_px_fonts:
        issues.append(f"{fixed_px_fonts} police(s) < 16px en style inline (lisibilité mobile)")

    return {
        "hasViewportMeta": has_viewport,
        "viewportContent": vp_content[:200],
        "viewportBlocksZoom": blocks_zoom,
        "cssMediaQueries": media_queries,
        "imagesWithSrcset": imgs_srcset,
        "imagesTotal": imgs_total,
        "fixedPxFontDecls": fixed_px_fonts,
        "largeFixedWidthDecls": large_fixed_widths,
        "issues": issues,
    }


def a11y_score(a11y: dict) -> int:
    """Rough 0-100 accessibility score from the static signals."""
    score = 100
    if not a11y.get("htmlHasLang"):
        score -= 8
    if not a11y.get("landmarksPresent"):
        score -= 6
    imgs = a11y.get("imagesTotal") or 0
    if imgs:
        ratio_no_alt = (a11y.get("imagesWithoutAlt") or 0) / imgs
        score -= round(ratio_no_alt * 25)
    inputs = a11y.get("formInputsTotal") or 0
    if inputs:
        ratio_no_label = (a11y.get("formInputsWithoutLabel") or 0) / inputs
        score -= round(ratio_no_label * 20)
    if a11y.get("buttonsAsDiv"):
        score -= min(12, a11y["buttonsAsDiv"] * 3)
    if a11y.get("linksEmpty"):
        score -= min(8, a11y["linksEmpty"] * 2)
    if a11y.get("linksGeneric"):
        score -= min(6, a11y["linksGeneric"])
    if a11y.get("h1Count", 0) != 1:
        score -= 5
    if a11y.get("headingOrderIssues"):
        score -= min(8, a11y["headingOrderIssues"] * 2)
    if a11y.get("positiveTabindex"):
        score -= min(8, a11y["positiveTabindex"] * 2)
    if a11y.get("iframeWithoutTitle"):
        score -= min(6, a11y["iframeWithoutTitle"] * 2)
    if a11y.get("ariaInvalidCount"):
        score -= min(6, a11y["ariaInvalidCount"])
    return max(0, min(100, score))
