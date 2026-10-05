"""Resolución de rutas: convierte lo que dice el usuario en rutas absolutas y normalizadas.

Es la ÚNICA forma de interpretar rutas: la usan las herramientas de archivos y el
sistema de permisos, para que ambos hablen de las mismas rutas.
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


def base_dirs() -> list[Path]:
    """Carpetas donde se busca una ruta relativa, en orden de preferencia."""
    home = Path.home()
    bases: list[Path] = []
    for base in (default_dir(), home / "Documents", home / "Desktop", home / "Downloads"):
        if base not in bases:
            bases.append(base)
    return bases


def _clean(text: str) -> str:
    cleaned = os.path.expandvars(text.strip().strip("\"'"))
    # '\Descargas' o '/Descargas' (barra inicial, sin unidad) se trata como relativa;
    # '\\servidor\carpeta' (red) no.
    if cleaned[:1] in ("\\", "/") and not cleaned.startswith(("\\\\", "//")):
        cleaned = cleaned.lstrip("\\/")
    if not cleaned:
        raise ValueError("la ruta está vacía")
    return cleaned


def candidate_paths(text: str) -> list[Path]:
    """Todas las rutas a las que puede referirse el texto, de la más a la menos preferida.

    - Absoluta: una sola, normalizada ('..', mayúsculas, enlaces).
    - 'escritorio\\notas': una sola, dentro del perfil de usuario.
    - Relativa ('pruebas', 'proyecto\\notas.txt'): una por cada carpeta base (ver base_dirs).
    Lanza ValueError si la ruta no es válida.
    """
    cleaned = _clean(text)
    try:
        path = Path(cleaned).expanduser()
        if path.drive and not path.is_absolute():
            raise ValueError("ruta con unidad pero sin ubicación completa")
        if path.is_absolute():
            return [path.resolve()]

        parts = [part for part in re.split(r"[\\/]+", cleaned) if part]
        if not parts:
            raise ValueError("la ruta está vacía")

        folder = KNOWN_FOLDERS.get(parts[0].lower())
        if folder:
            return [(Path.home() / folder).joinpath(*parts[1:]).resolve()]

        candidates: list[Path] = []
        for base in base_dirs():
            candidate = base.joinpath(*parts).resolve()
            if candidate not in candidates:
                candidates.append(candidate)
        return candidates
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"no se pudo interpretar la ruta ({exc})") from exc


def resolve_user_path(text: str) -> Path:
    """La ruta preferida (para crear cosas nuevas). Lanza ValueError si no es válida."""
    return candidate_paths(text)[0]


def resolve_existing(text: str) -> Path:
    """Para rutas que ya deberían existir: la primera candidata que existe (o la preferida)."""
    candidates = candidate_paths(text)
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def is_root_folder(path: Path) -> bool:
    """True para carpetas que nunca se deben copiar, mover ni renombrar enteras."""
    roots = {Path.home(), default_dir(), *(Path.home() / name for name in KNOWN_FOLDERS.values())}
    resolved = {root.resolve() for root in roots}
    return path == Path(path.anchor) or path in resolved