"""Herramientas básicas de Windows (solo librería estándar)."""
from __future__ import annotations

import getpass
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path

from core.paths import KNOWN_FOLDERS
from core.tool_registry import GROUP_MONITOR, RiskLevel, ToolParameter, registry
from services.process_manager import format_processes, normalize_sort, top_processes
from services.system_monitor import format_snapshot, normalize_part, take_snapshot

DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
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
    target_name = KNOWN_FOLDERS.get(folder.strip().lower())
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

@registry.register(
    name="system_status",
    description=(
        "Muestra el estado actual del equipo: uso de CPU, RAM, GPU y VRAM, disco y batería. "
        "Úsala para '¿cuánta RAM estoy usando?', '¿cómo está mi GPU?' o '¿cuánta batería me queda?'."
    ),
    risk=RiskLevel.SAFE,
    group=GROUP_MONITOR,
    parameters=[
        ToolParameter(
            "part",
            "string",
            "Qué mostrar: cpu, ram, gpu, disco o bateria. Si se omite, muestra todo",
            required=False,
        )
    ],
)
def system_status(part: str = "all") -> str:
    return format_snapshot(take_snapshot(), normalize_part(part))


@registry.register(
    name="process_list",
    description=(
        "Lista los programas (procesos) que más memoria o CPU consumen ahora mismo. "
        "Úsala para '¿qué está consumiendo más memoria?' o '¿qué usa más CPU?'."
    ),
    risk=RiskLevel.SAFE,
    group=GROUP_MONITOR,
    parameters=[
        ToolParameter(
            "sort_by",
            "string",
            "Ordenar por 'memoria' o 'cpu'. Si se omite, ordena por memoria",
            required=False,
        )
    ],
)
def process_list(sort_by: str = "memory") -> str:
    by = normalize_sort(sort_by)
    return format_processes(top_processes(by), by)