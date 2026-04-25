"""HTTPBasic password gate.

Single shared password set via APP_PASSWORD env var. Designed for one-agency
private deployments — not multi-tenant. When APP_PASSWORD is unset the gate
is permissive (dev mode), so the API behaves like before.

Use as a router-level dependency:

    from api.services.auth import require_auth
    router = APIRouter(dependencies=[Depends(require_auth)])

Or per-endpoint:

    @router.post("", dependencies=[Depends(require_auth)])
"""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from api.config import get_settings

_basic = HTTPBasic(auto_error=False)


def require_auth(
    credentials: Optional[HTTPBasicCredentials] = Depends(_basic),
) -> None:
    """Raise 401 unless credentials match APP_PASSWORD. No-op when unset."""
    expected = get_settings().auth_password
    if not expected:
        # Dev mode — auth disabled.
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mot de passe requis.",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Constant-time comparison to dodge timing attacks.
    if not secrets.compare_digest(credentials.password.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mot de passe incorrect.",
            headers={"WWW-Authenticate": "Basic"},
        )
