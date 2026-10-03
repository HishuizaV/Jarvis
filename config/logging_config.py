"""Configuración de logs: log general rotativo y registro de auditoría (JSON por línea)."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from typing import Any

from config.settings import BASE_DIR

LOGS_DIR = BASE_DIR / "logs"
audit_logger = logging.getLogger("jarvis.audit")

_SENSITIVE_KEY = re.compile(r"pass|pwd|token|secret|api[_-]?key|credential|contrase", re.IGNORECASE)
_SENSITIVE_TEXT = re.compile(
    r"\b(contraseña|contrasena|password|clave|token|secret)\b\s*(?:es|:|=)?\s*\S+",
    re.IGNORECASE,
)

_configured = False


def redact_text(text: str) -> str:
    """Enmascara lo que parece una contraseña o token: 'mi contraseña es x' -> 'mi contraseña ***'."""
    return _SENSITIVE_TEXT.sub(lambda match: f"{match.group(1)} ***", text)


def redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Copia de los argumentos sin valores sensibles (por nombre o por contenido)."""
    clean: dict[str, Any] = {}
    for key, value in arguments.items():
        if _SENSITIVE_KEY.search(key):
            clean[key] = "***"
        elif isinstance(value, str):
            clean[key] = redact_text(value)
        else:
            clean[key] = value
    return clean


def setup_logging(level: int = logging.INFO) -> None:
    """Configura los logs en logs/. Llamar una sola vez al iniciar la aplicación."""
    global _configured
    if _configured:
        return

    LOGS_DIR.mkdir(exist_ok=True)

    general = RotatingFileHandler(
        LOGS_DIR / "jarvis.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    general.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(general)
    root.addHandler(console)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    audit = RotatingFileHandler(
        LOGS_DIR / "audit.jsonl", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    audit.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(audit)
    audit_logger.propagate = False  # no duplicar la auditoría en jarvis.log

    _configured = True