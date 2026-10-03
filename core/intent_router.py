"""Interpreta un mensaje del usuario y decide: ¿herramienta o conversación?"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from core.ollama_client import Message, OllamaClient
from core.tool_registry import ToolError, ToolRegistry, registry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres JARVIS, un asistente de escritorio para Windows. "
    "Responde siempre en español y de forma breve. "
    "Usa una herramienta SOLO cuando el usuario pida explícitamente una acción "
    "sobre el equipo (abrir, cerrar, crear, mover, consultar el sistema, etc.). "
    "Para saludos, preguntas generales o conversación, responde con texto "
    "y NO uses herramientas."
)

# Palabras (sin tildes, en minúscula) que indican que el mensaje pide algo sobre el equipo.
TOOL_KEYWORDS = (
    # acciones
    "abre", "abrir", "cierra", "cerrar", "crea", "crear", "busca", "buscar",
    "encuentra", "mueve", "mover", "copia", "copiar", "renombra", "renombrar",
    "ejecuta", "ejecutar", "elimina", "eliminar", "borra", "borrar",
    "apaga", "apagar", "reinicia", "reiniciar", "recuerdame", "recordatorio",
    "avisame", "captura", "bloquea", "bloquear", "abierto", "abierta", "ejecutando",
    # consultas del sistema
    "ram", "cpu", "gpu", "bateria", "memoria", "procesador", "procesos",
    "hora", "fecha", "volumen", "disco", "consumiendo", "sistema",
)
_TOOL_PATTERN = re.compile(r"\b(?:" + "|".join(TOOL_KEYWORDS) + r")\b")


def normalize_text(text: str) -> str:
    """Minúsculas y sin tildes: 'Batería' -> 'bateria'."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def needs_tools(text: str) -> bool:
    """Compuerta en código: ¿vale la pena ofrecerle herramientas al modelo?"""
    return _TOOL_PATTERN.search(normalize_text(text)) is not None


@dataclass(frozen=True)
class ToolCall:
    """Una herramienta que el modelo quiere ejecutar, con sus argumentos."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Intent:
    """Decisión del router: ejecutar 'tool_call' o simplemente responder 'reply'."""

    tool_call: ToolCall | None = None
    reply: str = ""


class IntentRouter:
    """Pregunta al modelo y convierte su respuesta en un Intent."""

    def __init__(
        self,
        client: OllamaClient,
        tool_registry: ToolRegistry = registry,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self._client = client
        self._registry = tool_registry
        self._system_prompt = system_prompt

    def route(self, user_text: str, history: list[Message] | None = None) -> Intent:
        """Interpreta el mensaje del usuario. Puede lanzar OllamaError."""
        use_tools = needs_tools(user_text)

        # Al pedir herramientas no se envía el historial: un modelo de 3B arrastra
        # errores de turnos anteriores (por ejemplo, repite un argumento viejo).
        context = [] if use_tools else (history or [])
        messages: list[Message] = [
            {"role": "system", "content": self._system_prompt},
            *context,
            {"role": "user", "content": user_text},
        ]

        tools = self._registry.to_ollama_tools() if use_tools else []
        message = self._client.chat(messages, tools=tools or None, temperature=0.0)

        if not use_tools:
            # Aunque el modelo pida una herramienta, no se la ofrecimos: se ignora.
            return Intent(reply=(message.get("content") or "").strip())
        return self.parse_message(message)

    def parse_message(self, message: Message) -> Intent:
        """Convierte la respuesta cruda del modelo en un Intent."""
        calls = message.get("tool_calls") or []
        if not calls:
            return Intent(reply=(message.get("content") or "").strip())

        if len(calls) > 1:
            logger.warning("El modelo pidió %d herramientas; se usa solo la primera.", len(calls))

        function = calls[0].get("function", {})
        name = function.get("name", "")
        arguments = function.get("arguments")

        try:
            self._registry.get(name)
        except ToolError:
            logger.warning("El modelo pidió una herramienta inexistente: %r", name)
            return Intent(reply="No tengo una herramienta para eso.")

        return Intent(
            tool_call=ToolCall(name, arguments if isinstance(arguments, dict) else {})
        )