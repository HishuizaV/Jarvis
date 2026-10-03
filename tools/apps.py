"""Control de aplicaciones: abrir, cerrar y consultar si están en ejecución.

Solo se manejan las apps del catálogo config/apps.json (lista blanca): el modelo
nunca puede pasar un ejecutable o una ruta arbitraria.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import psutil

from config.settings import BASE_DIR
from core.tool_registry import RiskLevel, ToolParameter, registry

logger = logging.getLogger(__name__)

APPS_FILE = BASE_DIR / "config" / "apps.json"
TASKKILL_NOT_FOUND = 128  # código de salida de taskkill cuando el proceso no existe


class AppConfigError(Exception):
    """El catálogo de aplicaciones es inválido."""


@dataclass(frozen=True)
class AppEntry:
    """Una aplicación del catálogo."""

    name: str
    launch: str                      # nombre de programa, comando o protocolo (spotify:)
    process: str                     # nombre del proceso (Spotify.exe)
    aliases: tuple[str, ...] = ()
    can_close: bool = True
    force_close: bool = False        # True si la app no acepta cierre suave


def _key(text: str) -> str:
    """Normaliza lo que dice el usuario: minúsculas, sin espacios extra, sin '.exe'."""
    return " ".join(text.lower().split()).removesuffix(".exe")


class AppCatalog:
    """Catálogo de aplicaciones conocidas, con búsqueda por nombre o alias."""

    def __init__(self, entries: list[AppEntry]) -> None:
        self._entries = entries
        self._by_alias: dict[str, AppEntry] = {}
        for entry in entries:
            for alias in (entry.name, *entry.aliases):
                key = _key(alias)
                if self._by_alias.get(key, entry) is not entry:
                    raise AppConfigError(f"El alias '{alias}' está repetido en dos aplicaciones.")
                self._by_alias[key] = entry

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppCatalog:
        entries = []
        for name, raw in data.items():
            try:
                entries.append(
                    AppEntry(
                        name=name,
                        launch=raw["launch"],
                        process=raw["process"],
                        aliases=tuple(raw.get("aliases", [])),
                        can_close=bool(raw.get("can_close", True)),
                        force_close=bool(raw.get("force_close", False)),
                    )
                )
            except (KeyError, TypeError, AttributeError) as exc:
                raise AppConfigError(f"Entrada inválida para '{name}': {exc!r}") from exc
        return cls(entries)

    @classmethod
    def from_file(cls, path: Path) -> AppCatalog:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AppConfigError(f"No se pudo leer {path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise AppConfigError(f"{path.name} debe contener un objeto JSON.")
        return cls.from_dict(data)

    def find(self, query: str) -> AppEntry | None:
        return self._by_alias.get(_key(query))

    def entries(self) -> list[AppEntry]:
        return list(self._entries)

    def names(self) -> list[str]:
        return sorted(entry.name for entry in self._entries)


@lru_cache(maxsize=1)
def get_catalog() -> AppCatalog:
    """Carga el catálogo una sola vez."""
    return AppCatalog.from_file(APPS_FILE)


def _unknown(app: str) -> str:
    return f"No conozco la aplicación '{app}'. Puedo manejar: {', '.join(get_catalog().names())}."


def _is_process_running(process_name: str) -> bool:
    wanted = process_name.lower()
    return any(
        (proc.info["name"] or "").lower() == wanted for proc in psutil.process_iter(["name"])
    )


@registry.register(
    name="open_app",
    description="Abre una aplicación por su nombre. Ejemplos: spotify, chrome, vscode, whatsapp, calculadora, bloc de notas.",
    risk=RiskLevel.SAFE,
    parameters=[ToolParameter("app", "string", "Nombre de la aplicación")],
)
def open_app(app: str) -> str:
    entry = get_catalog().find(app)
    if entry is None:
        return _unknown(app)
    try:
        os.startfile(entry.launch)  # solo existe en Windows
    except OSError as exc:
        logger.warning("No se pudo abrir %s (%s): %s", entry.name, entry.launch, exc)
        return (
            f"No pude abrir {entry.name}: {exc}. "
            f"Revisa su entrada en config/apps.json."
        )
    return f"Abriendo {entry.name}."


@registry.register(
    name="close_app",
    description="Cierra una aplicación por su nombre. Ejemplos: spotify, chrome, vscode, calculadora.",
    risk=RiskLevel.SAFE,
    parameters=[ToolParameter("app", "string", "Nombre de la aplicación")],
)
def close_app(app: str) -> str:
    entry = get_catalog().find(app)
    if entry is None:
        return _unknown(app)
    if not entry.can_close:
        return f"Por seguridad no cierro {entry.name}: podría cerrar a JARVIS."

    command = ["taskkill", "/IM", entry.process]
    if entry.force_close:
        command.append("/F")
    result = subprocess.run(command, capture_output=True, text=True, check=False)

    if result.returncode == 0:
        return f"Le pedí a {entry.name} que se cierre."
    if result.returncode == TASKKILL_NOT_FOUND:
        return f"{entry.name} no está en ejecución."
    logger.warning("taskkill devolvió %s: %s", result.returncode, result.stderr.strip())
    return f"No pude cerrar {entry.name} (código {result.returncode})."


@registry.register(
    name="is_app_running",
    description="Indica si una aplicación está abierta (en ejecución).",
    risk=RiskLevel.SAFE,
    parameters=[ToolParameter("app", "string", "Nombre de la aplicación")],
)
def is_app_running(app: str) -> str:
    entry = get_catalog().find(app)
    if entry is None:
        return _unknown(app)
    state = "está" if _is_process_running(entry.process) else "no está"
    return f"{entry.name} {state} en ejecución."