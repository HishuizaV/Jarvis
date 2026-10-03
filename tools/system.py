"""Herramientas básicas de Windows (solo librería estándar)."""
from __future__ import annotations

import getpass
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path

from core.tool_registry import RiskLevel, ToolParameter, registry

DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

# Nombre que dice el usuario -> carpeta dentro del perfil de usuario.
SPECIAL_FOLDERS = {
    "escritorio": "Desktop", "desktop": "Desktop",
    "documentos": "Documents", "documents": "Documents",
    "descargas": "Downloads", "downloads": "Downloads",
    "imagenes": "Pictures", "imágenes": "Pictures", "fotos": "Pictures", "pictures": "Pictures",
    "musica": "Music", "música": "Music", "music": "Music",
    "videos": "Videos", "vídeos": "Videos",
}
FOLDER_HELP = "escritorio, documentos, descargas, imágenes, música o videos"


@registry.register(
    name="get_current_time",
    description="Devuelve la fecha y la hora actuales del equipo.",
    risk=RiskLevel.SAFE,
)
def get_current_time() -> str:
    now = datetime.now()
    return f"Hoy es {DAYS[now.weekday()]} {now:%d/%m/%Y} y son las {now:%H:%M}."


@registry.register(
    name="get_system_info",
    description="Muestra datos básicos del equipo: nombre, usuario, versión de Windows y arquitectura.",
    risk=RiskLevel.SAFE,
)
def get_system_info() -> str:
    return (
        f"Equipo: {platform.node()} | Usuario: {getpass.getuser()} | "
        f"Sistema: {platform.system()} {platform.release()} (versión {platform.version()}) | "
        f"Arquitectura: {platform.machine()} | Python {platform.python_version()}"
    )


@registry.register(
    name="open_special_folder",
    description=f"Abre una carpeta común de Windows en el Explorador: {FOLDER_HELP}.",
    risk=RiskLevel.SAFE,
    parameters=[
        ToolParameter("folder", "string", f"Nombre de la carpeta: {FOLDER_HELP}"),
    ],
)
def open_special_folder(folder: str) -> str:
    target_name = SPECIAL_FOLDERS.get(folder.strip().lower())
    if target_name is None:
        return f"No conozco la carpeta '{folder}'. Puedo abrir: {FOLDER_HELP}."

    path = Path.home() / target_name
    if not path.is_dir():
        return f"La carpeta '{folder}' no existe en {path}."

    os.startfile(path)  # solo existe en Windows
    return f"Abrí la carpeta {folder.strip()} ({path})."


@registry.register(
    name="lock_screen",
    description="Bloquea la sesión de Windows (pantalla de bloqueo).",
    risk=RiskLevel.CONFIRMATION_REQUIRED,
)
def lock_screen() -> str:
    subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
    return "Bloqueando la sesión."