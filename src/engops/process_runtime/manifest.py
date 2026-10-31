"""Declarative process manifest: inputs, outputs and the operation dependency map.

Stored as JSON on each ProcessVersion. Example:

    {
      "inputs":     [{"role": "source", "label": "Source file", "required": true,
                      "extensions": [".xlsx"]}],
      "outputs":    [{"role": "report", "label": "Report", "required": true}],
      "operations": [{"id": "build", "label": "Build report", "requires": ["source"]}]
    }
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from engops.process_runtime.errors import ManifestError

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


@dataclass(frozen=True)
class InputSpec:
    role: str
    label: str
    required: bool = True
    extensions: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class OutputSpec:
    role: str
    label: str
    required: bool = True


@dataclass(frozen=True)
class OperationSpec:
    id: str
    label: str
    requires: tuple[str, ...] = ()  # input roles this operation depends on


@dataclass(frozen=True)
class SkippedOperation:
    operation_id: str
    label: str
    reason: str


@dataclass(frozen=True)
class OperationPlan:
    enabled: tuple[OperationSpec, ...]
    skipped: tuple[SkippedOperation, ...]

    def is_enabled(self, operation_id: str) -> bool:
        return any(op.id == operation_id for op in self.enabled)


@dataclass(frozen=True)
class ProcessManifest:
    inputs: tuple[InputSpec, ...] = ()
    outputs: tuple[OutputSpec, ...] = ()
    operations: tuple[OperationSpec, ...] = ()

    # ------------------------------------------------------------------ parsing

    @classmethod
    def from_dict(cls, data: Any) -> "ProcessManifest":
        if not isinstance(data, dict):
            raise ManifestError("A manifest must be an object.")

        inputs = tuple(_parse_input(item) for item in _entries(data, "inputs"))
        outputs = tuple(_parse_output(item) for item in _entries(data, "outputs"))
        operations = tuple(_parse_operation(item) for item in _entries(data, "operations"))

        _ensure_unique("input role", [i.role for i in inputs])
        _ensure_unique("output role", [o.role for o in outputs])
        _ensure_unique("operation id", [op.id for op in operations])

        input_roles = {i.role for i in inputs}
        for op in operations:
            for role in op.requires:
                if role not in input_roles:
                    raise ManifestError(
                        f"Operation {op.id!r} requires unknown input role {role!r}."
                    )
        return cls(inputs, outputs, operations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputs": [
                {
                    "role": i.role,
                    "label": i.label,
                    "required": i.required,
                    "extensions": list(i.extensions),
                    "description": i.description,
                }
                for i in self.inputs
            ],
            "outputs": [
                {"role": o.role, "label": o.label, "required": o.required} for o in self.outputs
            ],
            "operations": [
                {"id": op.id, "label": op.label, "requires": list(op.requires)}
                for op in self.operations
            ],
        }

    # ------------------------------------------------------------------ queries

    def input_spec(self, role: str) -> InputSpec | None:
        return next((i for i in self.inputs if i.role == role), None)

    def output_spec(self, role: str) -> OutputSpec | None:
        return next((o for o in self.outputs if o.role == role), None)

    def plan(self, available_roles: Collection[str]) -> OperationPlan:
        """Which operations can run with the inputs we have, and which must be skipped."""
        available = set(available_roles)
        labels = {spec.role: spec.label for spec in self.inputs}
        enabled: list[OperationSpec] = []
        skipped: list[SkippedOperation] = []
        for op in self.operations:
            missing = [role for role in op.requires if role not in available]
            if missing:
                names = ", ".join(labels[role] for role in missing)
                skipped.append(SkippedOperation(op.id, op.label, f"missing input: {names}"))
            else:
                enabled.append(op)
        return OperationPlan(tuple(enabled), tuple(skipped))


# ---------------------------------------------------------------------- helpers


def _entries(data: dict, key: str) -> list[dict]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ManifestError(f"'{key}' must be a list.")
    for item in value:
        if not isinstance(item, dict):
            raise ManifestError(f"Every entry in '{key}' must be an object.")
    return value


def _identifier(item: dict, key: str, what: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ManifestError(
            f"Invalid {what} {value!r}: use lowercase letters, digits and underscores, "
            "starting with a letter."
        )
    return value


def _text(item: dict, key: str) -> str:
    value = item.get(key, "")
    if not isinstance(value, str):
        raise ManifestError(f"'{key}' must be text.")
    return value.strip()


def _flag(item: dict, key: str) -> bool:
    value = item.get(key, True)
    if not isinstance(value, bool):
        raise ManifestError(f"'{key}' must be true or false.")
    return value


def _extensions(item: dict) -> tuple[str, ...]:
    raw = item.get("extensions", [])
    if not isinstance(raw, list):
        raise ManifestError("'extensions' must be a list.")
    result: list[str] = []
    for ext in raw:
        if not isinstance(ext, str) or not ext.startswith(".") or len(ext) < 2:
            raise ManifestError(f"Invalid file extension {ext!r}: it must look like '.xlsx'.")
        result.append(ext.lower())
    return tuple(result)


def _parse_input(item: dict) -> InputSpec:
    role = _identifier(item, "role", "input role")
    return InputSpec(
        role=role,
        label=_text(item, "label") or role,
        required=_flag(item, "required"),
        extensions=_extensions(item),
        description=_text(item, "description"),
    )


def _parse_output(item: dict) -> OutputSpec:
    role = _identifier(item, "role", "output role")
    return OutputSpec(role=role, label=_text(item, "label") or role, required=_flag(item, "required"))


def _parse_operation(item: dict) -> OperationSpec:
    op_id = _identifier(item, "id", "operation id")
    requires = item.get("requires", [])
    if not isinstance(requires, list) or not all(isinstance(r, str) for r in requires):
        raise ManifestError("'requires' must be a list of input roles.")
    return OperationSpec(id=op_id, label=_text(item, "label") or op_id, requires=tuple(requires))


def _ensure_unique(kind: str, values: list[str]) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ManifestError(f"Duplicate {kind}: {value!r}")
        seen.add(value)