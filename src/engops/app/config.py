"""User/app settings stored as a small JSON file (atomic writes, corruption-safe)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

log = logging.getLogger(__name__)

SETTINGS_SCHEMA_VERSION = 1


@dataclass
class Settings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    window_width: int = 1200
    window_height: int = 780
    last_page: str = "overview"

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings file must contain a JSON object")
        except (OSError, ValueError) as exc:
            log.warning("Could not read settings (%s); using defaults.", exc)
            _quarantine(path)
            return cls()

        known = {f.name for f in fields(cls)}
        settings = cls(**{k: v for k, v in raw.items() if k in known})
        settings._sanitize(cls())
        return settings

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(tmp, path)  # atomic: never leaves a half-written settings file

    def _sanitize(self, defaults: "Settings") -> None:
        for name, minimum in (("window_width", 640), ("window_height", 420)):
            try:
                value = int(getattr(self, name))
            except (TypeError, ValueError):
                value = getattr(defaults, name)
            setattr(self, name, max(value, minimum))
        if not isinstance(self.last_page, str):
            self.last_page = defaults.last_page
        self.schema_version = SETTINGS_SCHEMA_VERSION


def _quarantine(path: Path) -> None:
    """Keep the unreadable file for inspection instead of silently destroying it."""
    try:
        path.replace(path.with_name(path.name + ".corrupt"))
    except OSError:
        log.exception("Could not quarantine corrupt settings file")