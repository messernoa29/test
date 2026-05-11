"""In-memory per-job progress log.

The audit pipeline pushes short status lines here keyed by job id; the
frontend polls /audit/{id}/logs to show a live "what's happening" panel
on the pending page. Process-local, capped, best-effort — if the process
restarts the log is gone (the audit itself is in the store).
"""

from __future__ import annotations

import threading
import time
from collections import deque

_MAX_LINES = 200
_lock = threading.Lock()
_logs: dict[str, deque] = {}


def add(job_id: str, message: str) -> None:
    """Append a timestamped line for this job."""
    if not job_id:
        return
    line = {"t": round(time.time(), 3), "msg": str(message)}
    with _lock:
        dq = _logs.get(job_id)
        if dq is None:
            dq = deque(maxlen=_MAX_LINES)
            _logs[job_id] = dq
        dq.append(line)


def get(job_id: str) -> list[dict]:
    with _lock:
        dq = _logs.get(job_id)
        return list(dq) if dq else []


def clear(job_id: str) -> None:
    with _lock:
        _logs.pop(job_id, None)
