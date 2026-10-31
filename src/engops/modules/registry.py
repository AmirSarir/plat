"""Module registry: stable IDs, versions, dependencies, enabled flags.

Feature flags control visibility only. They are NOT a security control.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class ModuleRegistryError(ValueError):
    pass


_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ModuleInfo:
    id: str
    name: str
    version: str
    description: str
    priority: str = "P0"
    dependencies: tuple[str, ...] = ()
    enabled: bool = True


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, ModuleInfo] = {}

    def register(self, info: ModuleInfo) -> None:
        if not _ID_RE.match(info.id):
            raise ModuleRegistryError(f"Invalid module id: {info.id!r}")
        if info.id in self._modules:
            raise ModuleRegistryError(f"Duplicate module id: {info.id!r}")
        self._modules[info.id] = info

    def get(self, module_id: str) -> ModuleInfo:
        try:
            return self._modules[module_id]
        except KeyError:
            raise ModuleRegistryError(f"Unknown module: {module_id!r}") from None

    def all(self) -> list[ModuleInfo]:
        return list(self._modules.values())

    def enabled_modules(self) -> list[ModuleInfo]:
        return [m for m in self._modules.values() if m.enabled]

    def validate(self) -> None:
        """Every enabled module must have all its dependencies registered and enabled."""
        for module in self.enabled_modules():
            for dep in module.dependencies:
                if dep not in self._modules:
                    raise ModuleRegistryError(
                        f"Module {module.id!r} depends on unknown module {dep!r}"
                    )
                if not self._modules[dep].enabled:
                    raise ModuleRegistryError(
                        f"Module {module.id!r} depends on disabled module {dep!r}"
                    )