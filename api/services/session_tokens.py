"""Opaque session tokens — so the password never sits in the browser.

On login the client posts the shared password to /auth/token and gets back
a random opaque token (stored process-side with an expiry). Subsequent
requests send `Authorization: Bearer <token>`. Restarting the backend
invalidates all tokens (acceptable for a single-agency tool); HTTP Basic
with the raw password still works as a fallback.

Not a JWT — we don't need claims, just an unguessable handle.
"""

from __future__ import annotations

import secrets
import threading
import time

_TTL_SECONDS = 7 * 24 * 3600  # 1 week
_lock = threading.Lock()
# token -> expiry epoch
_tokens: dict[str, float] = {}


def _prune(now: float) -> None:
    expired = [t for t, exp in _tokens.items() if exp <= now]
    for t in expired:
        _tokens.pop(t, None)


def issue() -> tuple[str, int]:
    """Create a new token. Returns (token, ttl_seconds)."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        _prune(now)
        _tokens[token] = now + _TTL_SECONDS
    return token, _TTL_SECONDS


def is_valid(token: str) -> bool:
    if not token:
        return False
    now = time.time()
    with _lock:
        exp = _tokens.get(token)
        if exp is None:
            return False
        if exp <= now:
            _tokens.pop(token, None)
            return False
        return True


def revoke(token: str) -> None:
    with _lock:
        _tokens.pop(token, None)
