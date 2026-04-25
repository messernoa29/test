"""Persistent storage for the agency branding (name, logo, accent colour).

Stored on disk under `api/data/branding/`:
- `branding.json` — name, tagline, website, accent, logo relative path
- `logo.<ext>`     — uploaded logo file

The file-based store keeps setup dead simple (no DB), survives a restart,
and can be migrated to S3/Postgres later without touching the route layer.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from api.models import AgencyBranding

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "branding"
_JSON_PATH = _DATA_DIR / "branding.json"
_LOGO_BASENAME = "logo"

_ALLOWED_LOGO_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

_lock = Lock()


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def load() -> AgencyBranding:
    """Return the current branding or an empty one."""
    with _lock:
        if not _JSON_PATH.exists():
            return AgencyBranding()
        try:
            raw = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Branding JSON unreadable, returning empty: %s", e)
            return AgencyBranding()
    try:
        return AgencyBranding.model_validate(raw)
    except Exception as e:
        logger.warning("Branding JSON invalid, returning empty: %s", e)
        return AgencyBranding()


def save(update: AgencyBranding) -> AgencyBranding:
    """Full replace of the stored branding.

    Text fields (name / tagline / website / accentColor) are written verbatim
    from the payload — passing `null` clears them. `logoUrl` is managed by
    the logo-upload flow so we never overwrite it from a regular save call;
    it is preserved from the current state.
    """
    current = load()

    merged = update.model_copy(
        update={
            "logoUrl": current.logoUrl,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
    )

    if merged.accentColor and not _HEX_COLOR_RE.match(merged.accentColor):
        raise ValueError(
            f"Couleur invalide : {merged.accentColor!r}. Attendu un hex #RRGGBB."
        )

    with _lock:
        _ensure_dir()
        _JSON_PATH.write_text(
            merged.model_dump_json(exclude_none=True, indent=2),
            encoding="utf-8",
        )
    return merged


def _patch_logo_url(new_url: Optional[str]) -> AgencyBranding:
    """Update only the `logoUrl` field; used by save_logo / clear_logo."""
    current = load()
    merged = current.model_copy(
        update={
            "logoUrl": new_url,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
    )
    with _lock:
        _ensure_dir()
        _JSON_PATH.write_text(
            merged.model_dump_json(exclude_none=True, indent=2),
            encoding="utf-8",
        )
    return merged


def clear_logo() -> AgencyBranding:
    """Delete the stored logo file and wipe the pointer in the JSON."""
    with _lock:
        _ensure_dir()
        for p in _DATA_DIR.glob(f"{_LOGO_BASENAME}.*"):
            try:
                p.unlink()
            except OSError as e:
                logger.warning("Could not delete logo %s: %s", p, e)
    return _patch_logo_url(None)


def save_logo(data: bytes, content_type: str) -> AgencyBranding:
    """Persist the uploaded logo and update the branding record."""
    if len(data) == 0:
        raise ValueError("Fichier vide")
    if len(data) > _MAX_LOGO_BYTES:
        raise ValueError(
            f"Logo trop lourd ({len(data) // 1024} KB). Maximum : "
            f"{_MAX_LOGO_BYTES // 1024} KB."
        )
    ext = _ALLOWED_LOGO_EXT.get(content_type.lower())
    if ext is None:
        raise ValueError(
            f"Format {content_type!r} non supporté. "
            "Utilisez PNG, JPEG, WebP ou SVG."
        )

    with _lock:
        _ensure_dir()
        # Remove any previous logo (different extension) first.
        for p in _DATA_DIR.glob(f"{_LOGO_BASENAME}.*"):
            try:
                p.unlink()
            except OSError as e:
                logger.warning("Could not delete previous logo %s: %s", p, e)
        target = _DATA_DIR / f"{_LOGO_BASENAME}.{ext}"
        target.write_bytes(data)

    # Public URL served by the route — cache-busted with updatedAt timestamp.
    logo_url = f"/settings/branding/logo?v={int(datetime.now(timezone.utc).timestamp())}"
    return _patch_logo_url(logo_url)


def logo_path() -> Optional[Path]:
    """Resolve the on-disk path to the stored logo, if any."""
    with _lock:
        _ensure_dir()
        for p in _DATA_DIR.glob(f"{_LOGO_BASENAME}.*"):
            if p.is_file():
                return p
    return None


def logo_content_type(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")
