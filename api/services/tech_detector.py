"""Lightweight, pure-Python tech-stack fingerprinting.

`detect_tech_stack(html, headers)` scans the raw HTML (and optionally the
response headers) for well-known markers — meta generators, CDN domains,
analytics snippets, ad pixels, chat/CRM widgets, hosting headers — and
returns a `ProspectStackByCategory`.

Confidence model:
- "high"   → an explicit, unambiguous fingerprint (e.g. `meta name="generator"
  content="WordPress …"`, `cdn.shopify.com`, a `fbq(` call).
- "medium" → a strong but indirect signal (asset path, library file name).
- "low"    → a heuristic deduction (a header that *often* but not always means
  a given provider).

The function never raises: bad/None input yields an empty result.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.models import DetectedTech, ProspectStackByCategory

logger = logging.getLogger(__name__)


def detect_tech_stack(
    html: Optional[str], headers: Optional[dict] = None,
) -> ProspectStackByCategory:
    """Best-effort fingerprint of the site's tech stack."""
    stack = ProspectStackByCategory()
    try:
        text = (html or "")
        low = text.lower()
        hdr = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        hdr_blob = " ".join(f"{k}: {v}" for k, v in hdr.items()).lower()

        _detect_cms(low, stack)
        _detect_analytics(low, stack)
        _detect_advertising(low, stack)
        _detect_chat_crm(low, stack)
        _detect_hosting(low, hdr, hdr_blob, stack)
    except Exception as e:  # never let fingerprinting break the pipeline
        logger.warning("tech_detector failed: %s", e)
    return stack


# ---------------------------------------------------------------------------
# Category detectors


def _detect_cms(low: str, stack: ProspectStackByCategory) -> None:
    # Explicit meta generator wins.
    gen = _meta_generator(low)
    if gen:
        gl = gen.lower()
        known = {
            "wordpress": "WordPress",
            "shopify": "Shopify",
            "wix": "Wix",
            "squarespace": "Squarespace",
            "webflow": "Webflow",
            "drupal": "Drupal",
            "joomla": "Joomla",
            "ghost": "Ghost",
            "prestashop": "PrestaShop",
            "magento": "Magento",
            "hubspot": "HubSpot CMS",
        }
        for needle, name in known.items():
            if needle in gl:
                stack.cms.append(
                    DetectedTech(
                        category="cms",
                        name=name,
                        confidence="high",
                        evidence=f'meta generator : "{gen[:120]}"',
                    )
                )
                break
        else:
            stack.cms.append(
                DetectedTech(
                    category="cms",
                    name=gen[:80],
                    confidence="medium",
                    evidence=f'meta generator : "{gen[:120]}"',
                )
            )

    have = {t.name.lower() for t in stack.cms}

    # Asset / markup heuristics (medium unless we already have a high hit).
    def add(name: str, conf: str, evidence: str) -> None:
        if name.lower() not in have:
            stack.cms.append(
                DetectedTech(category="cms", name=name, confidence=conf, evidence=evidence)
            )
            have.add(name.lower())

    if "/wp-content/" in low or "/wp-includes/" in low or "wp-json" in low:
        add("WordPress", "medium", "chemin d'asset /wp-content/ ou /wp-json")
    if "cdn.shopify.com" in low or "myshopify.com" in low or "shopify.theme" in low:
        add("Shopify", "high", "asset cdn.shopify.com / domaine myshopify.com")
    if "data-wf-page" in low or "data-wf-site" in low or ".webflow.io" in low or "assets.website-files.com" in low:
        add("Webflow", "high", "attribut data-wf-* ou domaine .webflow.io")
    if "static.wixstatic.com" in low or "wix.com" in low or "_wixCssImports".lower() in low:
        add("Wix", "high", "asset wixstatic.com / wix.com")
    if "static1.squarespace.com" in low or "squarespace.com" in low or "static.squarespace.com" in low:
        add("Squarespace", "high", "asset squarespace.com")
    if "/sites/default/files/" in low or 'name="generator" content="drupal' in low:
        add("Drupal", "medium", "chemin /sites/default/files/")
    if "framerusercontent.com" in low or "framer.app" in low:
        add("Framer", "medium", "asset framerusercontent.com")


def _detect_analytics(low: str, stack: ProspectStackByCategory) -> None:
    def add(name: str, conf: str, evidence: str) -> None:
        stack.analytics.append(
            DetectedTech(category="analytics", name=name, confidence=conf, evidence=evidence)
        )

    if "gtag/js?id=g-" in low or "googletagmanager.com/gtag/js?id=g-" in low:
        add("Google Analytics 4 (gtag)", "high", "script gtag/js?id=G-…")
    elif "google-analytics.com/analytics.js" in low or "ga('create'".lower() in low:
        add("Google Analytics (Universal)", "high", "analytics.js / ga('create')")
    if "googletagmanager.com/gtm.js" in low or "gtm-" in low and "googletagmanager" in low:
        add("Google Tag Manager", "high", "script googletagmanager.com/gtm.js")
    if "matomo" in low or "piwik" in low:
        add("Matomo / Piwik", "high", "script matomo / piwik")
    if "plausible.io" in low:
        add("Plausible", "high", "script plausible.io")
    if "static.cloudflareinsights.com" in low or "cloudflareinsights.com/beacon" in low:
        add("Cloudflare Web Analytics", "high", "beacon cloudflareinsights.com")
    if "hotjar.com" in low or "static.hotjar.com" in low or "hjsetting" in low:
        add("Hotjar", "high", "script hotjar.com")
    if "cdn.segment.com/analytics.js" in low or "segment.com/analytics.js" in low:
        add("Segment", "high", "script cdn.segment.com")
    if "clarity.ms" in low:
        add("Microsoft Clarity", "high", "script clarity.ms")


def _detect_advertising(low: str, stack: ProspectStackByCategory) -> None:
    def add(name: str, conf: str, evidence: str) -> None:
        stack.advertising.append(
            DetectedTech(category="advertising", name=name, confidence=conf, evidence=evidence)
        )

    if "connect.facebook.net" in low or "fbevents.js" in low or "fbq(" in low:
        add("Meta Pixel (Facebook)", "high", "fbevents.js / fbq(")
    if "googleadservices.com" in low or "google_conversion" in low or "gtag/js?id=aw-" in low or "/pagead/conversion" in low:
        add("Google Ads (conversion)", "high", "googleadservices.com / google_conversion")
    if "doubleclick.net" in low:
        add("Google DoubleClick", "medium", "domaine doubleclick.net")
    if "analytics.tiktok.com" in low or "tiktok.com/i18n/pixel" in low or "ttq.load" in low:
        add("TikTok Pixel", "high", "analytics.tiktok.com / ttq.load")
    if "snap.licdn.com" in low or "px.ads.linkedin.com" in low or "_linkedin_partner_id" in low:
        add("LinkedIn Insight Tag", "high", "snap.licdn.com / _linkedin_partner_id")
    if "sc-static.net" in low or "tr.snapchat.com" in low:
        add("Snapchat Pixel", "medium", "tr.snapchat.com")
    if "static.ads-twitter.com" in low or "platform.twitter.com/oct.js" in low:
        add("Twitter/X Pixel", "medium", "static.ads-twitter.com")
    if "bat.bing.com" in low:
        add("Microsoft Advertising (UET)", "high", "bat.bing.com/bat.js")


def _detect_chat_crm(low: str, stack: ProspectStackByCategory) -> None:
    def add(name: str, conf: str, evidence: str) -> None:
        stack.chatCrm.append(
            DetectedTech(category="chatCrm", name=name, confidence=conf, evidence=evidence)
        )

    if "widget.intercom.io" in low or "js.intercomcdn.com" in low or "intercom(" in low:
        add("Intercom", "high", "widget.intercom.io / Intercom(")
    if "crisp.chat" in low or "client.crisp.chat" in low or "$crisp" in low:
        add("Crisp", "high", "client.crisp.chat / $crisp")
    if "js.hs-scripts.com" in low or "js.hsforms.net" in low or "js.hubspot.com" in low or "hs-analytics" in low:
        add("HubSpot", "high", "js.hs-scripts.com / hsforms")
    if "js.driftt.com" in low or "drift.com" in low and "driftt" in low:
        add("Drift", "high", "js.driftt.com")
    if "embed.tawk.to" in low or "tawk.to" in low:
        add("Tawk.to", "high", "embed.tawk.to")
    if "widget.zopim.com" in low or "static.zdassets.com" in low or "zendesk.com/embeddable" in low:
        add("Zendesk Chat", "high", "static.zdassets.com / zopim")
    if "livechatinc.com" in low or "cdn.livechatinc.com" in low:
        add("LiveChat", "high", "cdn.livechatinc.com")
    if "salesforceliveagent" in low or "salesforce.com/embedded" in low:
        add("Salesforce", "medium", "salesforce embedded service")
    if "tidiochat" in low or "code.tidio.co" in low:
        add("Tidio", "high", "code.tidio.co")


def _detect_hosting(
    low: str, hdr: dict, hdr_blob: str, stack: ProspectStackByCategory,
) -> None:
    def add(name: str, conf: str, evidence: str) -> None:
        stack.hostingCdn.append(
            DetectedTech(category="hostingCdn", name=name, confidence=conf, evidence=evidence)
        )

    server = hdr.get("server", "").lower()
    powered = hdr.get("x-powered-by", "").lower()

    if "cf-ray" in hdr or "__cf_bm" in hdr_blob or server == "cloudflare":
        add("Cloudflare", "high", "header cf-ray / Server: cloudflare")
    elif "cdnjs.cloudflare.com" in low or "cdn-cgi/" in low:
        add("Cloudflare", "medium", "asset cdnjs / cdn-cgi/")
    if "x-vercel-id" in hdr or "x-vercel-cache" in hdr or server == "vercel" or ".vercel.app" in low:
        add("Vercel", "high", "header x-vercel-* / domaine .vercel.app")
    if "x-nf-request-id" in hdr or ".netlify.app" in low or server == "netlify":
        add("Netlify", "high", "header x-nf-request-id / domaine .netlify.app")
    if "x-amz-cf-id" in hdr or "cloudfront" in server or ".cloudfront.net" in low:
        add("AWS CloudFront", "high", "header x-amz-cf-id / cloudfront")
    if "x-github-request-id" in hdr or ".github.io" in low:
        add("GitHub Pages", "high", "header x-github-request-id / .github.io")
    if "fastly" in server or "x-served-by" in hdr and "fastly" in hdr_blob:
        add("Fastly", "medium", "header Server: fastly / x-served-by")
    if "x-fly-request-id" in hdr or ".fly.dev" in low:
        add("Fly.io", "high", "header x-fly-request-id")
    if server.startswith("nginx") and not stack.hostingCdn:
        add("nginx", "low", f"header Server: {server[:60]}")
    elif server.startswith("apache") and not stack.hostingCdn:
        add("Apache", "low", f"header Server: {server[:60]}")
    if "wpengine" in hdr_blob or "x-ac" in hdr and "wp" in hdr_blob:
        add("WP Engine", "medium", "header WP Engine")
    if powered:
        add(f"x-powered-by: {powered[:60]}", "low", f"header X-Powered-By: {powered[:80]}")


# ---------------------------------------------------------------------------
# Helpers


def _meta_generator(low: str) -> str:
    """Return the raw `content` of the first `meta name="generator"` tag."""
    try:
        idx = low.find('name="generator"')
        if idx < 0:
            idx = low.find("name='generator'")
        if idx < 0:
            return ""
        # find content attr near it (within the same tag)
        tag_end = low.find(">", idx)
        if tag_end < 0:
            tag_end = idx + 300
        segment = low[max(0, idx - 100) : tag_end + 1]
        ci = segment.find("content=")
        if ci < 0:
            return ""
        rest = segment[ci + len("content=") :].lstrip()
        if not rest:
            return ""
        quote = rest[0]
        if quote in ("'", '"'):
            end = rest.find(quote, 1)
            return rest[1:end].strip() if end > 0 else rest[1:].strip()
        # unquoted
        end = rest.find(" ")
        return (rest[:end] if end > 0 else rest).strip()
    except Exception:
        return ""
