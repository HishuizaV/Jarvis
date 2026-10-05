"""Lectura del estado del equipo: CPU, RAM, disco, batería y GPU NVIDIA."""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psutil

from core.text_utils import normalize_text

logger = logging.getLogger(__name__)

GB = 1024**3
NVIDIA_SMI_QUERY = "name,utilization.gpu,memory.used,memory.total,temperature.gpu"

PART_ALIASES = {
    "cpu": "cpu", "procesador": "cpu",
    "ram": "ram", "memoria": "ram",
    "gpu": "gpu", "grafica": "gpu", "vram": "gpu", "video": "gpu", "nvidia": "gpu",
    "disco": "disk", "disk": "disk", "almacenamiento": "disk",
    "bateria": "battery", "battery": "battery",
}


@dataclass(frozen=True)
class GpuInfo:
    """Estado de la GPU NVIDIA."""

    name: str
    utilization_percent: float
    memory_used_mb: float
    memory_total_mb: float
    temperature_c: float | None


@dataclass(frozen=True)
class SystemSnapshot:
    """Estado del equipo en un instante."""

    cpu_percent: float
    cpu_threads: int
    ram_used_gb: float
    ram_total_gb: float
    ram_percent: float
    disk_drive: str
    disk_used_gb: float
    disk_total_gb: float
    disk_percent: float
    battery_percent: float | None
    battery_plugged: bool | None
    gpu: GpuInfo | None


def _to_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def parse_gpu(output: str) -> GpuInfo | None:
    """Convierte la salida CSV de nvidia-smi (sin cabecera ni unidades) en GpuInfo."""
    lines = output.strip().splitlines()
    parts = [part.strip() for part in lines[0].split(",")] if lines else []
    if len(parts) != 5:
        return None
    try:
        return GpuInfo(
            name=parts[0],
            utilization_percent=float(parts[1]),
            memory_used_mb=float(parts[2]),
            memory_total_mb=float(parts[3]),
            temperature_c=_to_float(parts[4]),
        )
    except ValueError:
        return None


def read_gpu(timeout: float = 5.0) -> GpuInfo | None:
    """Lee la GPU con nvidia-smi. Si no está disponible, devuelve None."""
    try:
        result = subprocess.run(
            ["nvidia-smi", f"--query-gpu={NVIDIA_SMI_QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.info("nvidia-smi no disponible: %s", exc)
        return None
    if result.returncode != 0:
        logger.info("nvidia-smi terminó con error %s", result.returncode)
        return None
    return parse_gpu(result.stdout)


def take_snapshot(cpu_interval: float = 0.5) -> SystemSnapshot:
    """Mide el estado actual del equipo (la CPU se mide durante 'cpu_interval' segundos)."""
    memory = psutil.virtual_memory()
    drive = Path.home().anchor or "C:\\"
    disk = psutil.disk_usage(drive)
    battery = psutil.sensors_battery()
    return SystemSnapshot(
        cpu_percent=psutil.cpu_percent(interval=cpu_interval),
        cpu_threads=psutil.cpu_count(logical=True) or 0,
        ram_used_gb=memory.used / GB,
        ram_total_gb=memory.total / GB,
        ram_percent=memory.percent,
        disk_drive=drive,
        disk_used_gb=disk.used / GB,
        disk_total_gb=disk.total / GB,
        disk_percent=disk.percent,
        battery_percent=battery.percent if battery else None,
        battery_plugged=battery.power_plugged if battery else None,
        gpu=read_gpu(),
    )


def _cpu_line(s: SystemSnapshot) -> str:
    return f"CPU: {s.cpu_percent:.0f}% de uso ({s.cpu_threads} hilos)"


def _ram_line(s: SystemSnapshot) -> str:
    return f"RAM: {s.ram_used_gb:.1f} de {s.ram_total_gb:.1f} GB ({s.ram_percent:.0f}%)"


def _gpu_line(s: SystemSnapshot) -> str:
    gpu = s.gpu
    if gpu is None:
        return "GPU: no disponible (nvidia-smi no responde)."
    temperature = f", {gpu.temperature_c:.0f}°C" if gpu.temperature_c is not None else ""
    return (
        f"GPU {gpu.name}: {gpu.utilization_percent:.0f}% de uso, "
        f"VRAM {gpu.memory_used_mb / 1024:.1f} de {gpu.memory_total_mb / 1024:.1f} GB{temperature}"
    )


def _disk_line(s: SystemSnapshot) -> str:
    return (
        f"Disco {s.disk_drive}: {s.disk_used_gb:.0f} de {s.disk_total_gb:.0f} GB "
        f"({s.disk_percent:.0f}%)"
    )


def _battery_line(s: SystemSnapshot) -> str:
    if s.battery_percent is None:
        return "Batería: no detectada."
    state = "cargando" if s.battery_plugged else "con batería"
    return f"Batería: {s.battery_percent:.0f}% ({state})"


_LINES = {
    "cpu": _cpu_line,
    "ram": _ram_line,
    "gpu": _gpu_line,
    "disk": _disk_line,
    "battery": _battery_line,
}


def normalize_part(text: str) -> str:
    """Qué parte pidió el usuario: cpu, ram, gpu, disk, battery o all (si no se entiende)."""
    return PART_ALIASES.get(normalize_text(text).strip(), "all")


def format_snapshot(snapshot: SystemSnapshot, part: str = "all") -> str:
    """Texto para el usuario: una parte (cpu, ram, gpu, disk, battery) o todo."""
    if part in _LINES:
        return _LINES[part](snapshot)
    return "\n".join(line(snapshot) for line in _LINES.values())