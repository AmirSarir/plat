"""Errors raised by the process runtime."""

from engops.domain.errors import ValidationError


class ProcessRuntimeError(RuntimeError):
    """A process cannot be run (no approved version, no handler, bad use of the context...)."""


class ProcessInputError(ProcessRuntimeError):
    """A handler asked for an input that was not provided."""


class ManifestError(ValidationError):
    """A process manifest is malformed."""


class ProcessCancelled(Exception):
    """Raised by ProcessContext.check_cancelled() when the user cancelled the run."""