"""Pytest bootstrap.

Some backend modules (config, LLM providers) read env vars at import time and
raise if they're missing. The pure-function modules under test here do *not*
need that, but to keep the door open we load `api/.env` (simple KEY=VALUE
parse) with `setdefault` so existing environment always wins.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Ensure `import api...` works regardless of how pytest is invoked.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_dotenv() -> None:
    env_path = _REPO_ROOT / "api" / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv()
