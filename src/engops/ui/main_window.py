"""Main window: sidebar navigation + stacked pages (placeholders for now)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from engops import APP_TITLE
from engops.app.config import Settings
from engops.app.paths import AppPaths
from engops.modules.registry import ModuleInfo, ModuleRegistry

_NAV_STYLE = """
QListWidget#nav { font-size: 14px; border: none; background: #1f2933; color: #e4e7eb; }
QListWidget#nav::item { padding: 12px 16px; }
QListWidget#nav::item:selected { background: #3e4c59; color: white; }
"""


class PlaceholderPage(QWidget):
    def __init__(self, module: ModuleInfo) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(10)

        title = QLabel(module.name)
        font = title.font()
        font.setPointSize(20)
        font.setBold(True)
        title.setFont(font)

        meta = QLabel(f"Module ID: {module.id}  |  Version {module.version}  |  Priority {module.priority}")
        description = QLabel(module.description)
        description.setWordWrap(True)
        deps = ", ".join(module.dependencies) or "none"
        dependencies = QLabel(f"Depends on: {deps}")
        note = QLabel("Not implemented yet - this page is a placeholder.")

        for widget in (title, meta, description, dependencies, note):
            layout.addWidget(widget)
        layout.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(
        self,
        registry: ModuleRegistry,
        settings: Settings,
        paths: AppPaths,
        schema_version: int,
    ) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(settings.window_width, settings.window_height)

        self._module_ids: list[str] = []
        self._nav = QListWidget()
        self._nav.setObjectName("nav")
        self._nav.setFixedWidth(220)
        self._nav.setStyleSheet(_NAV_STYLE)
        self._stack = QStackedWidget()

        for module in registry.enabled_modules():
            item = QListWidgetItem(module.name)
            item.setData(Qt.ItemDataRole.UserRole, module.id)
            self._nav.addItem(item)
            self._stack.addWidget(PlaceholderPage(module))
            self._module_ids.append(module.id)

        # Connect first, then select, so the stack follows the restored selection.
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        start_row = (
            self._module_ids.index(settings.last_page)
            if settings.last_page in self._module_ids
            else 0
        )
        self._nav.setCurrentRow(start_row)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._nav)
        row.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self.statusBar().showMessage(
            f"Database schema v{schema_version}   |   Data folder: {paths.root}"
        )

    def capture_state(self, settings: Settings) -> None:
        """Copy window state into settings (the caller saves them)."""
        settings.window_width = self.width()
        settings.window_height = self.height()
        row = self._nav.currentRow()
        if 0 <= row < len(self._module_ids):
            settings.last_page = self._module_ids[row]