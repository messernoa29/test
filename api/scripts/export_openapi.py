"""Dump the FastAPI OpenAPI schema to openapi.json at the repo root.

Run from the repo root:  python -m api.scripts.export_openapi

The schema is the single source of truth for the API surface. Commit
openapi.json so type drift between api/models.py (Pydantic) and
lib/types.ts (hand-written) is visible in diffs. A future step can feed
this file to `openapi-typescript` to generate lib/api-schema.ts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    # Ensure env vars exist so api.main imports cleanly outside a real run.
    import os
    env_path = Path(__file__).resolve().parents[2] / "api" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)
    # Last-resort placeholders so config validation passes.
    os.environ.setdefault("LLM_PROVIDER", "gemini")
    os.environ.setdefault("GEMINI_API_KEY", "placeholder-for-schema-export")

    from api.main import app

    schema = app.openapi()
    out = Path(__file__).resolve().parents[2] / "openapi.json"
    out.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
