"""Small helpers shared by the domain and persistence layers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Timezone-aware UTC 'now', truncated to whole seconds (matches the stored format)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(_TS_FORMAT)


def from_iso(text: str) -> datetime:
    return datetime.strptime(text, _TS_FORMAT).replace(tzinfo=timezone.utc)