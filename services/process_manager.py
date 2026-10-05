"""Procesos en ejecución: los que más memoria o CPU consumen (agrupados por nombre)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import psutil

from core.text_utils import normalize_text

logger = logging.getLogger(__name__)

MB = 1024**2
IGNORED_PROCESSES = frozenset({"system idle process"})
CPU_ALIASES = frozenset({"cpu", "procesador"})


@dataclass(frozen=True)
class ProcessGroup:
    """Todos los procesos de un mismo programa, sumados."""

    name: str
    count: int
    memory_mb: float
    cpu_percent: float


def _measure_cpu(processes: list[Any], interval: float) -> dict[int, float]:
    """% de la CPU total (0-100) por PID, midiendo durante 'interval' segundos."""
    tracked = []
    for proc in processes:
        try:
            proc.cpu_percent(None)  # la primera llamada solo inicia la medición
            tracked.append(proc)
        except psutil.Error:
            continue

    time.sleep(interval)

    cores = psutil.cpu_count(logical=True) or 1
    usage: dict[int, float] = {}
    for proc in tracked:
        try:
            usage[proc.pid] = proc.cpu_percent(None) / cores
        except psutil.Error:
            continue
    return usage


def top_processes(by: str = "memory", limit: int = 5, cpu_interval: float = 0.5) -> list[ProcessGroup]:
    """Programas que más memoria ('memory') o CPU ('cpu') usan, sumando sus procesos."""
    processes = list(psutil.process_iter(["name", "memory_info"]))
    cpu_by_pid = _measure_cpu(processes, cpu_interval) if by == "cpu" else {}

    totals: dict[str, list[float]] = {}  # nombre -> [procesos, memoria_mb, cpu]
    for proc in processes:
        name = proc.info.get("name") or "desconocido"
        if name.lower() in IGNORED_PROCESSES:
            continue
        memory = proc.info.get("memory_info")
        entry = totals.setdefault(name, [0, 0.0, 0.0])
        entry[0] += 1
        entry[1] += memory.rss / MB if memory else 0.0
        entry[2] += cpu_by_pid.get(proc.pid, 0.0)

    groups = [
        ProcessGroup(name, int(count), memory_mb, cpu)
        for name, (count, memory_mb, cpu) in totals.items()
    ]
    key = (lambda g: g.cpu_percent) if by == "cpu" else (lambda g: g.memory_mb)
    return sorted(groups, key=key, reverse=True)[:limit]


def normalize_sort(text: str) -> str:
    """'cpu' si pidió CPU o procesador; en cualquier otro caso, 'memory'."""
    return "cpu" if normalize_text(text).strip() in CPU_ALIASES else "memory"


def _format_memory(megabytes: float) -> str:
    return f"{megabytes / 1024:.1f} GB" if megabytes >= 1024 else f"{megabytes:.0f} MB"


def format_processes(groups: list[ProcessGroup], by: str = "memory") -> str:
    """Lista numerada para el usuario."""
    if not groups:
        return "No pude leer la lista de procesos."

    lines = []
    for index, group in enumerate(groups, start=1):
        count = f" ({group.count} procesos)" if group.count > 1 else ""
        value = f"{group.cpu_percent:.1f}% de CPU" if by == "cpu" else _format_memory(group.memory_mb)
        lines.append(f"{index}. {group.name}{count}: {value}")

    header = (
        "Programas que más CPU usan ahora:"
        if by == "cpu"
        else "Programas que más memoria usan (aproximado):"
    )
    return "\n".join([header, *lines])