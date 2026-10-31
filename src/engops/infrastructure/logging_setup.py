"""Local rotating log file. No remote logging, no telemetry."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_MARK = "_engops_handler"


def configure_logging(logs_dir: Path, level: int = logging.INFO) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):  # avoid duplicates if called twice
        if getattr(handler, _MARK, False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(
        logs_dir / "engops.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    setattr(file_handler, _MARK, True)
    root.addHandler(file_handler)

    if sys.stderr is not None:  # None in windowed (no-console) builds
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        setattr(console, _MARK, True)
        root.addHandler(console)