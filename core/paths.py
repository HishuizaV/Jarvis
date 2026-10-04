"""Resolución de rutas: convierte lo que dice el usuario en una ruta absoluta y normalizada.

Es la ÚNICA función que interpreta rutas: la usan las herramientas de archivos y el
sistema de permisos, para que ambos hablen de exactamente la misma ruta.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from config.settings import settings

# Nombre que dice el usuario -> carpeta dentro del perfil de usuario.
KNOWN_FOLDERS = {
    "escritorio": "Desktop", "desktop": "Desktop",
    "documentos": "Documents", "documents": "Documents",
    "descargas": "Downloads", "downloads": "Downloads",
    "imagenes": "Pictures", "imágenes": "Pictures", "pictures": "Pictures",
    "musica": "Music", "música": "Music", "music": "Music",
    "videos": "Videos", "vídeos": "Videos",
}


def default_dir() -> Path:
    """Carpeta base para rutas sin ubicación (por ejemplo, 'pruebas')."""
    if settings.default_dir:
        return Path(settings.default_dir)
    return Path.home() / "Documents"


def resolve_user_path(text: str) -> Path:
    """Convierte texto del usuario en una ruta absoluta y normalizada.

    - 'escritorio\\notas' -> carpeta conocida dentro del perfil de usuario.
    - 'pruebas' (relativa)  -> dentro de la carpeta base (default_dir).
    - Absolutas: se normalizan ('..', mayúsculas, enlaces).
    Lanza ValueError si la ruta no es válida.
    """
    cleaned = os.path.expandvars(text.strip().strip("\"'"))
    if not cleaned:
        raise ValueError("la ruta está vacía")

    try:
        path = Path(cleaned).expanduser()
        if path.drive and not path.is_absolute():
            raise ValueError("ruta con unidad pero sin ubicación completa")

        if not path.is_absolute():
            first, *rest = re.split(r"[\\/]+", cleaned)
            folder = KNOWN_FOLDERS.get(first.lower())
            if folder:
                path = (Path.home() / folder).joinpath(*rest)
            else:
                path = default_dir() / path
        return path.resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"no se pudo interpretar la ruta ({exc})") from exc


def is_root_folder(path: Path) -> bool:
    """True para carpetas que nunca se deben copiar, mover ni renombrar enteras."""
    roots = {Path.home(), default_dir(), *(Path.home() / name for name in KNOWN_FOLDERS.values())}
    resolved = {root.resolve() for root in roots}
    return path == Path(path.anchor) or path in resolved