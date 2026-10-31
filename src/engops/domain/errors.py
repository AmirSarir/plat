"""Domain-level errors, independent of any database or GUI library."""


class RepositoryError(RuntimeError):
    """A persistence operation failed."""


class DuplicateRecordError(RepositoryError):
    """A unique constraint was violated (e.g. a process slug already exists)."""


class RecordNotFoundError(RepositoryError):
    """The requested record does not exist."""


class ValidationError(ValueError):
    """User-supplied data is not acceptable."""