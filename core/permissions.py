"""Sistema de permisos: decide en código si una herramienta puede ejecutarse."""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.settings import BASE_DIR
from core.paths import candidate_paths
from core.tool_registry import RiskLevel, Tool

logger = logging.getLogger(__name__)

PERMISSIONS_FILE = BASE_DIR / "config" / "permissions.json"

# Convención: las herramientas nombran así sus argumentos para que las reglas apliquen.
PATH_ARGUMENTS = frozenset({"path", "source", "destination", "folder", "file"})
PROCESS_ARGUMENTS = frozenset({"app", "process"})
COMMAND_ARGUMENTS = frozenset({"command"})

_SEVERITY = {
    RiskLevel.SAFE: 0,
    RiskLevel.CONFIRMATION_REQUIRED: 1,
    RiskLevel.BLOCKED: 2,
}


class PermissionConfigError(Exception):
    """El archivo de permisos no se puede leer o es inválido."""


@dataclass(frozen=True)
class PermissionResult:
    """Resultado de una verificación de permisos."""

    allowed: bool
    risk: RiskLevel
    reason: str

    @property
    def needs_confirmation(self) -> bool:
        """True si falta que el usuario confirme explícitamente."""
        return not self.allowed and self.risk is RiskLevel.CONFIRMATION_REQUIRED


def _normalize_process(name: str) -> str:
    """'Explorer.EXE' -> 'explorer'."""
    cleaned = name.strip().lower()
    return cleaned[:-4] if cleaned.endswith(".exe") else cleaned


def _paths(values: list[str]) -> tuple[Path, ...]:
    """Rutas del JSON: se expanden las variables (%USERPROFILE%) y se normalizan."""
    return tuple(Path(os.path.expandvars(value)).resolve() for value in values)


@dataclass(frozen=True)
class PermissionPolicy:
    """Reglas de permisos. Solo pueden subir el riesgo, nunca bajarlo."""

    protected_paths: tuple[Path, ...] = ()
    allowed_roots: tuple[Path, ...] = ()
    protected_processes: frozenset[str] = frozenset()
    blocked_commands: tuple[re.Pattern[str], ...] = ()
    confirm_commands: tuple[re.Pattern[str], ...] = ()
    tool_overrides: dict[str, RiskLevel] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionPolicy:
        """Construye la política desde un diccionario (el contenido del JSON)."""
        try:
            return cls(
                protected_paths=_paths(data.get("protected_paths", [])),
                allowed_roots=_paths(data.get("allowed_roots", [])),
                protected_processes=frozenset(
                    _normalize_process(p) for p in data.get("protected_processes", [])
                ),
                blocked_commands=tuple(
                    re.compile(p, re.IGNORECASE) for p in data.get("blocked_command_patterns", [])
                ),
                confirm_commands=tuple(
                    re.compile(p, re.IGNORECASE) for p in data.get("confirm_command_patterns", [])
                ),
                tool_overrides={
                    name: RiskLevel(value)
                    for name, value in data.get("tool_overrides", {}).items()
                },
            )
        except (ValueError, TypeError, AttributeError, OSError, re.error) as exc:
            raise PermissionConfigError(f"Configuración de permisos inválida: {exc}") from exc

    def check(
        self,
        tool: Tool,
        arguments: dict[str, Any] | None = None,
        *,
        confirmed: bool = False,
    ) -> PermissionResult:
        """Decide si la herramienta puede ejecutarse con esos argumentos.

        'confirmed' solo debe ser True si el USUARIO confirmó esta acción.
        BLOCKED nunca se permite, aunque confirmed sea True.
        """
        risk, reason = self._assess(tool, arguments or {})

        if risk is RiskLevel.BLOCKED:
            allowed = False
        elif risk is RiskLevel.CONFIRMATION_REQUIRED:
            allowed = confirmed
        else:
            allowed = True

        logger.info(
            "Permiso para %s: riesgo=%s permitido=%s (%s)", tool.name, risk.value, allowed, reason
        )
        return PermissionResult(allowed, risk, reason)

    def _assess(self, tool: Tool, arguments: dict[str, Any]) -> tuple[RiskLevel, str]:
        """Riesgo final: el más alto entre la herramienta, la configuración y los argumentos."""
        risk, reason = tool.risk, f"riesgo base de '{tool.name}'"

        override = self.tool_overrides.get(tool.name)
        if override is not None and _SEVERITY[override] > _SEVERITY[risk]:
            risk, reason = override, "reforzado por la configuración de permisos"

        for found_risk, found_reason in self._argument_findings(arguments):
            if _SEVERITY[found_risk] > _SEVERITY[risk]:
                risk, reason = found_risk, found_reason
        return risk, reason

    def _argument_findings(self, arguments: dict[str, Any]) -> Iterator[tuple[RiskLevel, str]]:
        """Revisa los argumentos de texto contra las reglas."""
        for name, value in arguments.items():
            if not isinstance(value, str):
                continue
            if name in PATH_ARGUMENTS:
                yield from self._path_findings(name, value)
            if name in PROCESS_ARGUMENTS and _normalize_process(value) in self.protected_processes:
                yield RiskLevel.CONFIRMATION_REQUIRED, f"'{value}' es un proceso protegido"
            if name in COMMAND_ARGUMENTS:
                if any(pattern.search(value) for pattern in self.blocked_commands):
                    yield RiskLevel.BLOCKED, "el comando coincide con un patrón bloqueado"
                if any(pattern.search(value) for pattern in self.confirm_commands):
                    yield RiskLevel.CONFIRMATION_REQUIRED, "el comando coincide con un patrón que requiere confirmación"

    def _path_findings(self, name: str, value: str) -> Iterator[tuple[RiskLevel, str]]:
        """Evalúa una ruta tal como la interpretan las herramientas (core.paths)."""
        try:
            candidates = candidate_paths(value)
        except ValueError:
            yield RiskLevel.CONFIRMATION_REQUIRED, f"no se pudo interpretar la ruta del argumento '{name}'"
            return

        # Una ruta relativa puede terminar en varias carpetas base: se evalúan TODAS.
        if any(
            candidate.is_relative_to(protected)
            for candidate in candidates
            for protected in self.protected_paths
        ):
            yield RiskLevel.CONFIRMATION_REQUIRED, f"el argumento '{name}' apunta a una ruta protegida"
        elif self.allowed_roots and any(
            not any(candidate.is_relative_to(root) for root in self.allowed_roots)
            for candidate in candidates
        ):
            yield RiskLevel.CONFIRMATION_REQUIRED, f"el argumento '{name}' está fuera de tus carpetas permitidas"


def load_policy(path: Path = PERMISSIONS_FILE) -> PermissionPolicy:
    """Carga la política desde un JSON. Si el archivo es inválido, falla (no arranca sin protección)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PermissionConfigError(f"No se pudo leer {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise PermissionConfigError(f"{path.name} debe contener un objeto JSON.")
    return PermissionPolicy.from_dict(data)