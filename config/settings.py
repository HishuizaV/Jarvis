"""Configuración central de JARVIS (valores desde variables de entorno / .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """Ajustes de la aplicación. Se leen una sola vez al importar el módulo."""

    ollama_url: str = os.getenv("JARVIS_OLLAMA_URL", "http://localhost:11434")
    model: str = os.getenv("JARVIS_MODEL", "llama3.2:3b")
    keep_alive: str = os.getenv("JARVIS_KEEP_ALIVE", "5m")
    num_ctx: int = int(os.getenv("JARVIS_NUM_CTX", "4096"))
    timeout: float = float(os.getenv("JARVIS_TIMEOUT", "120"))
    default_dir: str = os.getenv("JARVIS_DEFAULT_DIR", "")


settings = Settings()