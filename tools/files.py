"""Herramientas de archivos: buscar, abrir, crear carpetas, copiar, mover y renombrar.

Reglas de seguridad en código (no dependen del modelo):
- Nunca se sobrescribe nada: si el destino existe, se avisa.
- No se copian, mueven ni renombran carpetas principales (usuario, Documentos, Escritorio...).
- No se abren ejecutables, scripts ni accesos directos.
Las rutas se interpretan con core.paths, igual que en el sistema de permisos.
"""
from __future__ import annotations

import functools
import logging
import os
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core import paths
from core.tool_registry import RiskLevel, ToolParameter, registry

logger = logging.getLogger(__name__)

RISKY_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse",
    ".wsf", ".scr", ".lnk", ".jar", ".reg", ".hta", ".cpl", ".docm", ".xlsm", ".pptm",
})
SKIP_DIRS = frozenset({
    "appdata", "node_modules", ".git", ".venv", "__pycache__", "$recycle.bin",
    "system volume information",
})
INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|]')
MAX_RESULTS = 10
SEARCH_TIME_LIMIT = 10.0  # segundos


class FileToolError(Exception):
    """Problema esperado con una operación de archivos; su mensaje se muestra al usuario."""


def _friendly(func: Callable[..., str]) -> Callable[..., str]:
    """Convierte los errores esperados en mensajes para el usuario (y los registra)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return func(*args, **kwargs)
        except FileToolError as exc:
            return str(exc)
        except OSError as exc:
            logger.warning("Fallo en %s: %s", func.__name__, exc)
            return f"No pude completar la operación: {exc}"

    return wrapper


def _resolve(text: str) -> Path:
    try:
        return paths.resolve_user_path(text)
    except ValueError as exc:
        raise FileToolError(f"No entendí la ruta '{text}': {exc}.") from exc


def _require_existing(path: Path) -> None:
    if not path.exists():
        raise FileToolError(f"No existe: {path}")


def _refuse_root(path: Path) -> None:
    if paths.is_root_folder(path):
        raise FileToolError(
            f"Por seguridad no copio, muevo ni renombro carpetas principales como {path}."
        )


def _destination(source: Path, destination_text: str) -> Path:
    """Calcula el destino de copiar o mover y verifica que sea seguro."""
    target = _resolve(destination_text)
    wants_folder = destination_text.strip().endswith(("\\", "/"))

    if target.is_dir():
        target = target / source.name
    elif wants_folder:
        raise FileToolError(f"La carpeta de destino no existe: {target}")

    if source.is_dir() and (target == source or source in target.parents):
        raise FileToolError("No puedo copiar o mover una carpeta dentro de sí misma.")
    if target.exists():
        raise FileToolError(f"Ya existe {target}. No sobrescribo nada: elige otro nombre o carpeta.")
    if not target.parent.is_dir():
        raise FileToolError(f"La carpeta de destino no existe: {target.parent}")
    return target


def _default_search_roots() -> list[Path]:
    """Dónde buscar si no se indica carpeta: la carpeta base, Escritorio y Descargas."""
    home = Path.home()
    roots: list[Path] = []
    for candidate in (paths.default_dir(), home / "Desktop", home / "Downloads"):
        if candidate.is_dir() and candidate.resolve() not in roots:
            roots.append(candidate.resolve())
    return roots


def _search(roots: list[Path], needle: str) -> tuple[list[Path], bool]:
    """Busca por nombre (sin distinguir mayúsculas). Devuelve (resultados, búsqueda_completa)."""
    deadline = time.monotonic() + SEARCH_TIME_LIMIT
    found: list[Path] = []
    for root in roots:
        for current, dirs, files in os.walk(root):
            dirs[:] = [name for name in dirs if name.casefold() not in SKIP_DIRS]
            for entry in (*dirs, *files):
                if needle in entry.casefold():
                    found.append(Path(current) / entry)
                    if len(found) >= MAX_RESULTS:
                        return found, False
            if time.monotonic() > deadline:
                return found, False
    return found, True


def _describe(path: Path) -> str:
    return f"{path}  [carpeta]" if path.is_dir() else str(path)


@registry.register(
    name="create_folder",
    description="Crea una carpeta. Acepta una ruta completa o solo un nombre.",
    risk=RiskLevel.SAFE,
    parameters=[ToolParameter("path", "string", "Ruta o nombre de la carpeta a crear")],
)
@_friendly
def create_folder(path: str) -> str:
    target = _resolve(path)
    if target.is_dir():
        return f"La carpeta ya existe: {target}"
    if target.exists():
        raise FileToolError(f"Ya existe un archivo con ese nombre: {target}")
    target.mkdir(parents=True)
    return f"Carpeta creada: {target}"


@registry.register(
    name="find_file",
    description="Busca archivos o carpetas por nombre (basta con parte del nombre). No abre nada.",
    risk=RiskLevel.SAFE,
    parameters=[
        ToolParameter("name", "string", "Nombre o parte del nombre a buscar, por ejemplo 'factura'"),
        ToolParameter(
            "folder",
            "string",
            "Carpeta donde buscar (opcional). Si se omite, busca en la carpeta base, Escritorio y Descargas",
            required=False,
        ),
    ],
)
@_friendly
def find_file(name: str, folder: str = "") -> str:
    needle = name.strip().casefold()
    if not needle:
        raise FileToolError("Dime qué archivo quieres buscar.")

    roots = [_resolve(folder)] if folder.strip() else _default_search_roots()
    found, complete = _search(roots, needle)
    if not found:
        places = ", ".join(str(root) for root in roots)
        return f"No encontré '{name}' en {places}."

    lines = [f"{index}. {_describe(path)}" for index, path in enumerate(found, start=1)]
    note = "" if complete else "\n(Hay más resultados o la búsqueda se cortó: sé más específico.)"
    return f"Encontré {len(found)} resultado(s):\n" + "\n".join(lines) + note


@registry.register(
    name="open_file",
    description=(
        "Abre un archivo o carpeta con su programa predeterminado. Acepta la ruta o solo el nombre. "
        "No abre programas ni scripts."
    ),
    risk=RiskLevel.SAFE,
    parameters=[ToolParameter("path", "string", "Ruta o nombre del archivo a abrir")],
)
@_friendly
def open_file(path: str) -> str:
    text = path.strip()
    target = _resolve(text)

    if not target.exists() and not re.search(r"[\\/]", text):
        matches, _ = _search(_default_search_roots(), text.casefold())
        if len(matches) > 1:
            options = "\n".join(f"  - {_describe(match)}" for match in matches)
            return (
                f"Encontré varios archivos para '{text}':\n{options}\n"
                "Dime la ruta completa del que quieres abrir."
            )
        if not matches:
            return f"No encontré '{text}'."
        target = matches[0]

    _require_existing(target)
    if target.is_file() and target.suffix.lower() in RISKY_EXTENSIONS:
        return f"Por seguridad no abro archivos {target.suffix}: podrían ejecutar código."

    os.startfile(target)  # solo existe en Windows
    return f"Abriendo {target}."


@registry.register(
    name="copy_file",
    description=(
        "Copia un archivo o carpeta sin sobrescribir nada. "
        "El destino puede ser una carpeta existente o un nombre nuevo."
    ),
    risk=RiskLevel.SAFE,
    parameters=[
        ToolParameter("source", "string", "Archivo o carpeta a copiar"),
        ToolParameter("destination", "string", "Carpeta de destino o nombre nuevo"),
    ],
)
@_friendly
def copy_file(source: str, destination: str) -> str:
    origin = _resolve(source)
    _require_existing(origin)
    _refuse_root(origin)
    target = _destination(origin, destination)

    if origin.is_dir():
        shutil.copytree(origin, target)
    else:
        shutil.copy2(origin, target)
    return f"Copiado a {target}."


@registry.register(
    name="move_file",
    description=(
        "Mueve un archivo o carpeta sin sobrescribir nada. "
        "El destino puede ser una carpeta existente o un nombre nuevo."
    ),
    risk=RiskLevel.SAFE,
    parameters=[
        ToolParameter("source", "string", "Archivo o carpeta a mover"),
        ToolParameter("destination", "string", "Carpeta de destino o nombre nuevo"),
    ],
)
@_friendly
def move_file(source: str, destination: str) -> str:
    origin = _resolve(source)
    _require_existing(origin)
    _refuse_root(origin)
    target = _destination(origin, destination)

    shutil.move(origin, target)
    return f"Movido a {target}."


@registry.register(
    name="rename_file",
    description="Cambia el nombre de un archivo o carpeta, sin moverlo de lugar.",
    risk=RiskLevel.SAFE,
    parameters=[
        ToolParameter("path", "string", "Archivo o carpeta a renombrar"),
        ToolParameter("new_name", "string", "Nuevo nombre (solo el nombre, sin ruta)"),
    ],
)
@_friendly
def rename_file(path: str, new_name: str) -> str:
    origin = _resolve(path)
    _require_existing(origin)
    _refuse_root(origin)

    name = new_name.strip()
    if not name or name in {".", ".."} or INVALID_NAME_CHARS.search(name):
        raise FileToolError(
            'El nuevo nombre no es válido: no puede estar vacío ni contener \\ / : * ? " < > |'
        )

    target = origin.with_name(name)
    if target.exists():
        raise FileToolError(f"Ya existe {target}. No sobrescribo nada.")
    origin.rename(target)
    return f"Renombrado a {target.name}."