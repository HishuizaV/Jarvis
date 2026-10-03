"""Agente principal: une el router, los permisos y las herramientas."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime

from config.logging_config import audit_logger, redact_arguments, redact_text
from core.intent_router import IntentRouter, ToolCall, normalize_text
from core.ollama_client import Message, OllamaError
from core.permissions import PermissionPolicy, load_policy
from core.tool_registry import ToolError, ToolRegistry, registry

logger = logging.getLogger(__name__)

MAX_HISTORY = 10          # mensajes recordados (el contexto del modelo es pequeño)
MAX_RESULT_CHARS = 500    # resultado máximo guardado en la auditoría

AFFIRMATIVE = frozenset({"si", "confirmo", "confirmar", "adelante", "hazlo", "dale"})
NEGATIVE = frozenset({"no", "cancela", "cancelar", "nunca", "detente"})


def parse_confirmation(text: str) -> bool | None:
    """True = confirma, False = rechaza, None = no es una respuesta de confirmación.

    Debe ser corta y empezar con una palabra afirmativa; cualquier 'no' la anula.
    """
    words = re.findall(r"[a-z]+", normalize_text(text))
    if not words:
        return None
    if any(word in NEGATIVE for word in words):
        return False
    if words[0] in AFFIRMATIVE and len(words) <= 4:
        return True
    return None


@dataclass(frozen=True)
class PendingAction:
    """Acción que espera la confirmación del usuario."""

    request: str
    tool_call: ToolCall


class Agent:
    """Procesa mensajes del usuario y ejecuta herramientas de forma segura."""

    def __init__(
        self,
        router: IntentRouter,
        tool_registry: ToolRegistry = registry,
        policy: PermissionPolicy | None = None,
    ) -> None:
        self._router = router
        self._registry = tool_registry
        self._policy = policy or load_policy()
        self._history: list[Message] = []
        self._pending: PendingAction | None = None

    @property
    def has_pending(self) -> bool:
        """True si hay una acción esperando confirmación."""
        return self._pending is not None

    def handle(self, user_text: str) -> str:
        """Procesa un mensaje del usuario y devuelve la respuesta de JARVIS."""
        text = user_text.strip()
        if not text:
            return "No recibí ningún mensaje. ¿Qué necesitas?"
        answer = self._handle(text)
        self._remember(text, answer)
        return answer

    def _handle(self, text: str) -> str:
        if self._pending is not None:
            # La confirmación vale para UN solo mensaje: se consume pase lo que pase.
            pending, self._pending = self._pending, None
            decision = parse_confirmation(text)
            if decision is True:
                return self._execute(pending.request, pending.tool_call, confirmed=True)
            self._audit(pending.request, pending.tool_call, "cancelled", result="No confirmada.")
            if decision is False:
                return "De acuerdo, acción cancelada."
            # No era una confirmación: se cancela lo pendiente y se atiende el mensaje nuevo.

        try:
            intent = self._router.route(text, self._history)
        except OllamaError as exc:
            logger.error("Fallo al consultar el modelo: %s", exc)
            self._audit(text, None, "error", error=str(exc))
            return "No pude comunicarme con el modelo de IA. ¿Está Ollama en ejecución?"

        if intent.tool_call is None:
            reply = intent.reply or "No tengo una respuesta para eso."
            self._audit(text, None, "chat", result=reply)
            return reply

        return self._execute(text, intent.tool_call, confirmed=False)

    def _execute(self, request: str, call: ToolCall, *, confirmed: bool) -> str:
        started = time.perf_counter()

        try:
            tool = self._registry.get(call.name)
            tool.validate_arguments(call.arguments)
        except ToolError as exc:
            self._audit(request, call, "rejected", error=str(exc), started=started)
            return f"No pude ejecutar eso: {exc}."

        verdict = self._policy.check(tool, call.arguments, confirmed=confirmed)

        if verdict.needs_confirmation:
            self._pending = PendingAction(request, call)
            self._audit(request, call, "confirmation_requested", error=verdict.reason, started=started)
            return (
                f"Esta acción requiere tu confirmación ({verdict.reason}):\n"
                f"  {call.name} {call.arguments}\n"
                "¿La ejecuto? (sí / no)"
            )

        if not verdict.allowed:  # única puerta de ejecución
            self._audit(request, call, "blocked", error=verdict.reason, started=started)
            return f"No puedo hacer eso: {verdict.reason}."

        try:
            result = str(tool.run(call.arguments))
        except Exception as exc:  # noqa: BLE001 - frontera de la app: se registra y no la cierra
            logger.exception("La herramienta %s falló", call.name)
            self._audit(
                request, call, "error", error=f"{type(exc).__name__}: {exc}", started=started
            )
            return f"La herramienta '{call.name}' falló: {exc}"

        decision = "executed_confirmed" if confirmed else "executed"
        self._audit(request, call, decision, result=result, started=started)
        return result

    def _remember(self, user_text: str, answer: str) -> None:
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": answer})
        self._history = self._history[-MAX_HISTORY:]

    def _audit(
        self,
        request: str,
        call: ToolCall | None,
        decision: str,
        *,
        result: str = "",
        error: str = "",
        started: float | None = None,
    ) -> None:
        """Escribe un registro de auditoría (sin contraseñas ni tokens)."""
        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "request": redact_text(request),
            "tool": call.name if call else None,
            "arguments": redact_arguments(call.arguments) if call else None,
            "decision": decision,
            "result": redact_text(result)[:MAX_RESULT_CHARS],
            "error": error or None,
            "duration_ms": round((time.perf_counter() - started) * 1000) if started else None,
        }
        audit_logger.info(json.dumps(record, ensure_ascii=False))