"""The handlers that ship with the app."""

from __future__ import annotations

from engops.process_runtime.demo import DemoEchoHandler
from engops.process_runtime.registry import HandlerRegistry


def build_handler_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register(DemoEchoHandler())
    return registry