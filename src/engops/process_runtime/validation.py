"""Generic input validation driven by the manifest."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from engops.process_runtime.manifest import ProcessManifest


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def label(self) -> str:
        return self.value.upper()


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    message: str
    role: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.WARNING)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def validate_inputs(manifest: ProcessManifest, provided: Mapping[str, Path]) -> ValidationReport:
    """Check the provided files against the manifest (roles, presence, extension, not empty)."""
    issues: list[ValidationIssue] = []

    for role in provided:
        if manifest.input_spec(role) is None:
            issues.append(
                ValidationIssue(Severity.ERROR, f"Unknown input '{role}' for this process.", role)
            )

    for spec in manifest.inputs:
        raw = provided.get(spec.role)
        if raw is None:
            if spec.required:
                issues.append(
                    ValidationIssue(
                        Severity.ERROR, f"Required input '{spec.label}' was not provided.", spec.role
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        Severity.INFO,
                        f"Optional input '{spec.label}' was not provided; "
                        "operations that need it will be skipped.",
                        spec.role,
                    )
                )
            continue

        path = Path(raw)
        if not path.is_file():
            issues.append(
                ValidationIssue(Severity.ERROR, f"'{spec.label}': file not found: {path}", spec.role)
            )
            continue
        if spec.extensions and path.suffix.lower() not in spec.extensions:
            issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    f"'{spec.label}': expected {', '.join(spec.extensions)} "
                    f"but got '{path.suffix or 'no extension'}'.",
                    spec.role,
                )
            )
        if path.stat().st_size == 0:
            issues.append(
                ValidationIssue(Severity.ERROR, f"'{spec.label}': file is empty.", spec.role)
            )

    return ValidationReport(tuple(issues))