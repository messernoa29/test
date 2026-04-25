"""Smoke-test the crawl → analyse pipeline against a real URL.

Usage:
    cd api && python -m scripts.test_pipeline https://www.lasource-foodschool.com
"""

from __future__ import annotations

import json
import sys

from api.services import analyzer, crawler


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.test_pipeline <url>", file=sys.stderr)
        return 2
    url = sys.argv[1]

    print(f"[1/2] Crawling {url} ...")
    crawl = crawler.crawl(url)
    print(f"      {len(crawl.pages)} pages crawled on {crawl.domain}")

    print("[2/2] Analysing ...")
    audit = analyzer.analyze(crawl)
    print(f"      Global score: {audit.globalScore} — {audit.globalVerdict}")
    print(f"      Critical: {audit.criticalCount}  Warnings: {audit.warningCount}")

    print("\n--- AUDIT_JSON ---")
    print(json.dumps(audit.model_dump(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
