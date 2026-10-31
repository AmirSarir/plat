"""Registry of approved process handlers. Only registered handlers can ever run."""

from __future__ import annotations

import re

from engops.process_runtime.contracts import BaseProcessHandler
from engops.process_runtime.errors import ProcessRuntimeError

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,59}$")


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, BaseProcessHandler] = {}

    def register(self, handler: BaseProcessHandler) -> None:
        if not isinstance(handler, BaseProcessHandler):
            raise ProcessRuntimeError("Only BaseProcessHandler subclasses can be registered.")
        slug = getattr(handler, "slug", None)
        if not isinstance(slug, str) or not _SLUG_RE.match(slug):
            raise ProcessRuntimeError(f"Handler has an invalid slug: {slug!r}")
        if slug in self._handlers:
            raise ProcessRuntimeError(f"A handler for {slug!r} is already registered.")
        self._handlers[slug] = handler

    def get(self, slug: str) -> BaseProcessHandler:
        try:
            return self._handlers[slug]
        except KeyError:
            raise ProcessRuntimeError(f"No handler registered for process {slug!r}.") from None

    def slugs(self) -> list[str]:
        return sorted(self._handlers)