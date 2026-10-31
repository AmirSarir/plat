"""Application start-up: paths -> logging -> settings -> context -> window."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from engops import APP_NAME, __version__
from engops.app.config import Settings
from engops.app.context import AppContext, create_context
from engops.app.paths import AppPaths, data_root
from engops.infrastructure.logging_setup import configure_logging
from engops.ui.main_window import MainWindow

log = logging.getLogger(__name__)


def _excepthook(exc_type, exc, tb) -> None:
    log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
    if QApplication.instance() is not None:
        QMessageBox.critical(None, APP_NAME, f"Unexpected error:\n{exc}\n\nDetails are in the log file.")


def run(argv: list[str] | None = None) -> int:
    paths = AppPaths(data_root())
    paths.ensure()
    configure_logging(paths.logs_dir)
    log.info("Starting %s %s (data: %s)", APP_NAME, __version__, paths.root)
    sys.excepthook = _excepthook

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)

    ctx: AppContext | None = None
    try:
        settings = Settings.load(paths.config_file)
        ctx = create_context(paths, settings)
        log.info("Instance id: %s", ctx.instance_id)

        window = MainWindow(ctx.registry, settings, paths, ctx.schema_version)
        # Temporary readout until the Overview module exists.
        window.statusBar().addPermanentWidget(
            QLabel(f"Processes: {ctx.processes.count()}  |  Runs: {ctx.runs.count()}")
        )
        window.show()
        code = app.exec()

        window.capture_state(settings)
        settings.save(paths.config_file)
        return code
    except Exception as exc:
        log.exception("Start-up failed")
        QMessageBox.critical(
            None,
            APP_NAME,
            f"The application could not start:\n{exc}\n\nLog folder:\n{paths.logs_dir}",
        )
        return 1
    finally:
        if ctx is not None:
            ctx.close()