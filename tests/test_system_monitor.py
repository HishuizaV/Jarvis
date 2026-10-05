"""Pruebas del monitor del sistema (sin leer el hardware real)."""
import subprocess
from types import SimpleNamespace

import psutil
import pytest

from services import system_monitor
from services.system_monitor import (
    GB,
    GpuInfo,
    SystemSnapshot,
    format_snapshot,
    normalize_part,
    parse_gpu,
    read_gpu,
    take_snapshot,
)

GPU_LINE = "NVIDIA GeForce RTX 3050 Laptop GPU, 12, 842, 4096, 51\n"


def make_snapshot(**changes) -> SystemSnapshot:
    data = dict(
        cpu_percent=23.4,
        cpu_threads=12,
        ram_used_gb=9.2,
        ram_total_gb=15.8,
        ram_percent=58.0,
        disk_drive="C:\\",
        disk_used_gb=392.6,
        disk_total_gb=475.6,
        disk_percent=82.5,
        battery_percent=76.0,
        battery_plugged=True,
        gpu=GpuInfo("NVIDIA GeForce RTX 3050 Laptop GPU", 12.0, 842.0, 4096.0, 51.0),
    )
    data.update(changes)
    return SystemSnapshot(**data)


def test_parse_gpu_lee_la_salida_de_nvidia_smi():
    gpu = parse_gpu(GPU_LINE)
    assert gpu == GpuInfo("NVIDIA GeForce RTX 3050 Laptop GPU", 12.0, 842.0, 4096.0, 51.0)


def test_parse_gpu_tolera_temperatura_no_disponible():
    gpu = parse_gpu("NVIDIA X, 5, 100, 4096, [N/A]")
    assert gpu is not None
    assert gpu.temperature_c is None


@pytest.mark.parametrize("output", ["", "basura", "a, b, c"])
def test_parse_gpu_con_salida_invalida(output):
    assert parse_gpu(output) is None


def test_read_gpu_ejecuta_nvidia_smi_sin_shell(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=GPU_LINE, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert read_gpu() is not None
    assert calls[0][0] == "nvidia-smi"


def test_read_gpu_sin_nvidia_smi(monkeypatch):
    def fake_run(args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert read_gpu() is None


def test_read_gpu_con_error(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda args, **kw: SimpleNamespace(returncode=9, stdout="", stderr="x")
    )
    assert read_gpu() is None


def patch_psutil(monkeypatch, battery):
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 30.0)
    monkeypatch.setattr(psutil, "cpu_count", lambda logical=True: 8)
    monkeypatch.setattr(
        psutil, "virtual_memory", lambda: SimpleNamespace(used=8 * GB, total=16 * GB, percent=50.0)
    )
    monkeypatch.setattr(
        psutil, "disk_usage", lambda path: SimpleNamespace(used=100 * GB, total=200 * GB, percent=50.0)
    )
    monkeypatch.setattr(psutil, "sensors_battery", lambda: battery)
    monkeypatch.setattr(system_monitor, "read_gpu", lambda: None)


def test_take_snapshot_combina_las_lecturas(monkeypatch):
    patch_psutil(monkeypatch, battery=None)

    snapshot = take_snapshot()

    assert snapshot.cpu_percent == 30.0
    assert snapshot.cpu_threads == 8
    assert (snapshot.ram_used_gb, snapshot.ram_total_gb) == (8.0, 16.0)
    assert snapshot.disk_percent == 50.0
    assert snapshot.battery_percent is None
    assert snapshot.gpu is None


def test_take_snapshot_con_bateria(monkeypatch):
    patch_psutil(monkeypatch, battery=SimpleNamespace(percent=76, power_plugged=True))

    snapshot = take_snapshot()

    assert snapshot.battery_percent == 76
    assert snapshot.battery_plugged is True


def test_format_snapshot_completo_incluye_todas_las_lineas():
    text = format_snapshot(make_snapshot())
    for word in ("CPU", "RAM", "GPU", "Disco", "Batería"):
        assert word in text


def test_format_snapshot_por_parte():
    snapshot = make_snapshot()
    assert format_snapshot(snapshot, "ram") == "RAM: 9.2 de 15.8 GB (58%)"
    assert "VRAM 0.8 de 4.0 GB" in format_snapshot(snapshot, "gpu")
    assert "CPU" not in format_snapshot(snapshot, "ram")


def test_format_snapshot_sin_gpu_ni_bateria():
    snapshot = make_snapshot(gpu=None, battery_percent=None, battery_plugged=None)
    assert "no disponible" in format_snapshot(snapshot, "gpu")
    assert "no detectada" in format_snapshot(snapshot, "battery")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("RAM", "ram"),
        ("memoria", "ram"),
        ("procesador", "cpu"),
        ("Batería", "battery"),
        ("vram", "gpu"),
        ("disco", "disk"),
        ("todo", "all"),
        ("", "all"),
        ("cosa rara", "all"),
    ],
)
def test_normalize_part(text, expected):
    assert normalize_part(text) == expected