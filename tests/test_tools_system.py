"""Pruebas de las herramientas básicas de Windows (sin abrir ventanas ni bloquear nada)."""
import os
import subprocess
from datetime import datetime
from pathlib import Path


from core.tool_registry import GROUP_MONITOR
from services.process_manager import ProcessGroup
from services.system_monitor import GpuInfo, SystemSnapshot
from tools.system import process_list, system_status
from core.tool_registry import RiskLevel, registry
from tools import load_tools
from tools.system import get_current_time, get_system_info, lock_screen, open_special_folder


def test_get_current_time_incluye_el_ano_actual():
    assert str(datetime.now().year) in get_current_time()


def test_get_system_info_incluye_python():
    assert "Python" in get_system_info()


def test_open_special_folder_abre_la_carpeta(monkeypatch, tmp_path):
    (tmp_path / "Downloads").mkdir()
    opened = []
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)

    result = open_special_folder("Descargas")

    assert opened == [tmp_path / "Downloads"]
    assert "Abrí" in result


def test_open_special_folder_rechaza_nombres_desconocidos(monkeypatch):
    opened = []
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)

    assert "No conozco" in open_special_folder("C:\\Windows")
    assert opened == []


def test_open_special_folder_avisa_si_la_carpeta_no_existe(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert "no existe" in open_special_folder("videos")


def test_lock_screen_llama_a_rundll32_sin_shell(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append(args))

    lock_screen()

    assert calls == [["rundll32.exe", "user32.dll,LockWorkStation"]]


def test_niveles_de_riesgo():
    load_tools()
    assert registry.get("lock_screen").risk is RiskLevel.CONFIRMATION_REQUIRED
    assert registry.get("open_special_folder").risk is RiskLevel.SAFE


def test_load_tools_registra_las_herramientas():
    load_tools()
    names = {tool.name for tool in registry.all()}
    assert {"get_current_time", "get_system_info", "open_special_folder", "lock_screen"} <= names

def test_system_status_usa_el_monitor_y_filtra_por_parte(monkeypatch):
    snapshot = SystemSnapshot(
        cpu_percent=10.0, cpu_threads=8, ram_used_gb=4.0, ram_total_gb=16.0, ram_percent=25.0,
        disk_drive="C:\\", disk_used_gb=100.0, disk_total_gb=200.0, disk_percent=50.0,
        battery_percent=None, battery_plugged=None,
        gpu=GpuInfo("GPU X", 1.0, 100.0, 4096.0, None),
    )
    monkeypatch.setattr("tools.system.take_snapshot", lambda: snapshot)

    assert system_status("ram").startswith("RAM")
    assert "CPU" in system_status()


def test_process_list_ordena_segun_el_parametro(monkeypatch):
    calls = []

    def fake_top(by):
        calls.append(by)
        return [ProcessGroup("a.exe", 1, 100.0, 5.0)]

    monkeypatch.setattr("tools.system.top_processes", fake_top)

    process_list("CPU")
    process_list()

    assert calls == ["cpu", "memory"]


def test_las_herramientas_de_monitor_son_seguras_y_tienen_su_grupo():
    load_tools()
    for name in ("system_status", "process_list"):
        tool = registry.get(name)
        assert tool.risk is RiskLevel.SAFE
        assert tool.group == GROUP_MONITOR