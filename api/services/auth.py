"""Auth gate for the API.

Single shared password set via APP_PASSWORD. Designed for one-agency
private deployments — not multi-tenant. When APP_PASSWORD is unset the
gate is permissive (dev mode), so the API behaves like before.

Two ways to authenticate:
  1. `Authorization: Bearer <session-token>` — issued by POST /auth/token
     in exchange for the password, so the raw password never persists in
     the browser. Preferred.
  2. HTTP Basic with the raw password — kept as a fallback / for tooling.

Use as a router-level dependency:

    from api.services.auth import require_auth
    router = APIRouter(dependencies=[Depends(require_auth)])

Or per-endpoint:

    @router.post("", dependencies=[Depends(require_auth)])
"""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from api.config import get_settings
from api.services import session_tokens

_basic = HTTPBasic(auto_error=False)


def _bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def require_auth(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(_basic),
) -> None:
    """Raise 401 unless a valid session token or the correct password is
    presented. No-op when APP_PASSWORD is unset (dev mode)."""
    expected = get_settings().auth_password
    if not expected:
        return  # dev mode — auth disabled

    # 1. Bearer session token.
    token = _bearer_token(request)
    if token is not None:
        if session_tokens.is_valid(token):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée — reconnectez-vous.",
        )

    # 2. HTTP Basic with the raw password.
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
            headers={"WWW-Authenticate": "Basic"},
        )
    # Constant-time comparison to dodge timing attacks.
    if not secrets.compare_digest(credentials.password.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mot de passe incorrect.",
            headers={"WWW-Authenticate": "Basic"},
        )


def verify_password(password: str) -> bool:
    """True if `password` matches APP_PASSWORD (or auth is disabled)."""
    expected = get_settings().auth_password
    if not expected:
        return True
    return secrets.compare_digest(password.encode(), expected.encode())
