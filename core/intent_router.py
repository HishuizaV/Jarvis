"""Interpreta un mensaje del usuario y decide: ¿herramienta o conversación?"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from core.ollama_client import Message, OllamaClient
from core.text_utils import normalize_text
from core.tool_registry import GROUP_FILES, ToolError, ToolRegistry, registry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres JARVIS, un asistente de escritorio para Windows. "
    "Responde siempre en español y de forma breve. "
    "Usa una herramienta SOLO cuando el usuario pida explícitamente una acción "
    "sobre el equipo (abrir, cerrar, crear, mover, consultar el sistema, etc.). "
    "Para saludos, preguntas generales o conversación, responde con texto "
    "y NO uses herramientas."
)

CHAT_PROMPT = (
    "Eres JARVIS, un asistente de escritorio para Windows. "
    "Responde siempre en español y de forma breve. "
    "En esta respuesta NO puedes ejecutar acciones: no abres, creas, copias, mueves "
    "ni modificas nada. Nunca digas que realizaste una acción. "
    "Si el usuario pide algo sobre su equipo, dile que lo escriba como una orden directa, "
    "por ejemplo «abre notas.txt» o «crea una carpeta llamada fotos»."
)

ACTION_CLAIM_WARNING = (
    "No ejecuté ninguna acción. Si quieres que haga algo, dímelo como una orden directa, "
    "por ejemplo: «abre notas.txt» o «crea una carpeta llamada fotos»."
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

# "archivo", "carpeta" o un nombre con extensión (script.bat, notas.txt; no versiones como 3.12).
_FILES_PATTERN = re.compile(
    r"\b(?:archivos?|carpetas?)\b|\b[\w-]+\.(?=[a-z0-9]*[a-z])[a-z0-9]{2,5}\b"
)

# Respuestas que afirman haber hecho algo (el modelo en conversación no hace nada: es mentira).
_ACTION_CLAIM = re.compile(
    r"\b(?:abri|abrio|escribio|movi"
    r"|(?:he|ha) (?:abierto|creado|copiado|movido|renombrado|escrito|eliminado|borrado"
    r"|cerrado|guardado|ejecutado))\b"
)


def needs_tools(text: str) -> bool:
    """Compuerta en código: ¿vale la pena ofrecerle herramientas al modelo?"""
    return _TOOL_PATTERN.search(normalize_text(text)) is not None


def mentions_files(text: str) -> bool:
    """True si el mensaje habla de archivos o carpetas (o trae un nombre con extensión)."""
    return _FILES_PATTERN.search(normalize_text(text)) is not None


def claims_action(reply: str) -> bool:
    """True si la respuesta dice que se hizo una acción ('Abrí...', 'He creado...')."""
    return _ACTION_CLAIM.search(normalize_text(reply)) is not None


def _clean_reply(content: str | None) -> str:
    """Texto de respuesta; descarta lo que afirma haber ejecutado algo que no se ejecutó."""
    reply = (content or "").strip()
    if claims_action(reply):
        logger.warning("Se descartó una respuesta que afirmaba haber ejecutado una acción.")
        return ACTION_CLAIM_WARNING
    return reply


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
        chat_prompt: str = CHAT_PROMPT,
    ) -> None:
        self._client = client
        self._registry = tool_registry
        self._system_prompt = system_prompt
        self._chat_prompt = chat_prompt

    def route(self, user_text: str, history: list[Message] | None = None) -> Intent:
        """Interpreta el mensaje del usuario. Puede lanzar OllamaError."""
        use_tools = needs_tools(user_text)

        # Al pedir herramientas no se envía el historial: un modelo de 3B arrastra
        # errores de turnos anteriores (por ejemplo, repite un argumento viejo).
        context = [] if use_tools else (history or [])
        prompt = self._system_prompt if use_tools else self._chat_prompt
        messages: list[Message] = [
            {"role": "system", "content": prompt},
            *context,
            {"role": "user", "content": user_text},
        ]

        tools: list[dict[str, Any]] = []
        if use_tools:
            # Si habla de archivos, solo se ofrecen las herramientas de archivos:
            # un modelo de 3B se confunde entre herramientas parecidas (open_app vs open_file).
            if mentions_files(user_text):
                tools = self._registry.to_ollama_tools(GROUP_FILES)
            tools = tools or self._registry.to_ollama_tools()

        message = self._client.chat(messages, tools=tools or None, temperature=0.0)

        if not use_tools:
            # Aunque el modelo pida una herramienta, no se la ofrecimos: se ignora.
            return Intent(reply=_clean_reply(message.get("content")))
        return self.parse_message(message)

    def parse_message(self, message: Message) -> Intent:
        """Convierte la respuesta cruda del modelo en un Intent."""
        calls = message.get("tool_calls") or []
        if not calls:
            return Intent(reply=_clean_reply(message.get("content")))

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