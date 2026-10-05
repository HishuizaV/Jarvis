"""Catálogo de herramientas que JARVIS puede usar."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

PYTHON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}

GROUP_FILES = "files"  # herramientas de archivos y carpetas

GROUP_MONITOR = "monitor"  # estado del equipo: CPU, RAM, GPU, procesos

class RiskLevel(str, Enum):
    """Nivel de riesgo de una herramienta."""

    SAFE = "safe"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


class ToolError(Exception):
    """Error al registrar, buscar o ejecutar una herramienta."""


@dataclass(frozen=True)
class ToolParameter:
    """Un argumento de una herramienta. 'type' usa nombres JSON: string, integer, number, boolean."""

    name: str
    type: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class Tool:
    """Una herramienta: función Python + metadatos que ve el modelo."""

    name: str
    description: str
    risk: RiskLevel
    func: Callable[..., Any]
    parameters: tuple[ToolParameter, ...] = ()
    group: str = ""

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        """Lanza ToolError si faltan argumentos, sobran o tienen el tipo incorrecto."""
        known = {param.name for param in self.parameters}
        unknown = set(arguments) - known
        if unknown:
            raise ToolError(f"'{self.name}' no acepta los argumentos: {sorted(unknown)}")

        for param in self.parameters:
            if param.name not in arguments:
                if param.required:
                    raise ToolError(f"'{self.name}' requiere el argumento '{param.name}'")
                continue
            value = arguments[param.name]
            expected = PYTHON_TYPES[param.type]
            # En Python, bool es subclase de int: no lo aceptamos como número.
            is_bool_as_number = isinstance(value, bool) and param.type != "boolean"
            if is_bool_as_number or not isinstance(value, expected):
                raise ToolError(
                    f"'{self.name}': el argumento '{param.name}' debe ser {param.type}"
                )

    def run(self, arguments: dict[str, Any] | None = None) -> Any:
        """Valida y ejecuta. NO revisa permisos: eso lo hace el Agent (fases 7-8)."""
        arguments = arguments or {}
        self.validate_arguments(arguments)
        return self.func(**arguments)

    def to_ollama_schema(self) -> dict[str, Any]:
        """Formato que Ollama espera para describir una herramienta al modelo."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        param.name: {"type": param.type, "description": param.description}
                        for param in self.parameters
                    },
                    "required": [param.name for param in self.parameters if param.required],
                },
            },
        }


class ToolRegistry:
    """Catálogo de herramientas disponibles."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        risk: RiskLevel,
        parameters: list[ToolParameter] | tuple[ToolParameter, ...] = (),
        group: str = "",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorador que registra una función como herramienta."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._tools:
                raise ToolError(f"Ya existe una herramienta llamada '{name}'")
            self._tools[name] = Tool(name, description, risk, func, tuple(parameters), group)
            logger.debug("Herramienta registrada: %s (%s)", name, risk.value)
            return func

        return decorator

    def get(self, name: str) -> Tool:
        """Busca una herramienta por nombre."""
        try:
            return self._tools[name]
        except KeyError:
            raise ToolError(f"La herramienta '{name}' no existe") from None

    def all(self) -> list[Tool]:
        """Todas las herramientas registradas."""
        return list(self._tools.values())

    def to_ollama_tools(self, group: str | None = None) -> list[dict[str, Any]]:
        """Esquemas para el modelo. Las BLOCKED no se muestran; con 'group', solo las de ese grupo."""
        return [
            tool.to_ollama_schema()
            for tool in self._tools.values()
            if tool.risk is not RiskLevel.BLOCKED and (group is None or tool.group == group)
        ]


registry = ToolRegistry()