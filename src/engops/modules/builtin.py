"""The built-in modules shipped with the app."""

from __future__ import annotations

from engops.modules.registry import ModuleInfo, ModuleRegistry


def build_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(
        ModuleInfo(
            id="overview",
            name="Overview",
            version="0.1.0",
            description="Quick actions, frequently used processes, recent local activity, "
            "warnings and shortcuts.",
        )
    )
    registry.register(
        ModuleInfo(
            id="process_library",
            name="Process Library",
            version="0.1.0",
            description="Approved process catalog with owner, purpose, inputs/outputs, "
            "validation, and a controlled run action.",
        )
    )
    registry.register(
        ModuleInfo(
            id="reference_catalog",
            name="Reference Catalog",
            version="0.1.0",
            description="Searchable people, sites, protocols, methods, datasets and "
            "the relationships between them.",
        )
    )
    registry.register(
        ModuleInfo(
            id="run_history",
            name="Run History",
            version="0.1.0",
            description="Status, timestamps, process version, input manifest, outputs, "
            "warnings and errors for every run.",
            priority="P1",
            dependencies=("process_library",),
        )
    )
    registry.validate()
    return registry