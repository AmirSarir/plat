"""Where the app keeps its local data. Everything lives under one folder."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from engops import APP_NAME


def data_root() -> Path:
    """Data folder. Override with the ENGOPS_HOME environment variable (handy for dev/tests)."""
    override = os.environ.get("ENGOPS_HOME")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    return Path.home() / ".engops"


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def db_file(self) -> Path:
        return self.root / "engops.sqlite3"

    @property
    def config_file(self) -> Path:
        return self.root / "settings.json"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def files_dir(self) -> Path:
        """Managed files (inputs, outputs, documents) - used from step 2 on."""
        return self.root / "files"

    @property
    def backups_dir(self) -> Path:
        return self.root / "backups"

    def ensure(self) -> None:
        for folder in (self.root, self.logs_dir, self.files_dir, self.backups_dir):
            folder.mkdir(parents=True, exist_ok=True)