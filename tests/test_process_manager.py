"""Pruebas del gestor de procesos (con procesos falsos)."""
import time
from types import SimpleNamespace

import psutil
import pytest

from services.process_manager import (
    ProcessGroup,
    format_processes,
    normalize_sort,
    top_processes,
)

MB = 1024**2


class FakeProc:
    def __init__(self, pid, name, rss_mb, cpu=(0.0, 0.0)):
        self.pid = pid
        memory = SimpleNamespace(rss=rss_mb * MB) if rss_mb is not None else None
        self.info = {"name": name, "memory_info": memory}
        self._cpu = iter(cpu)

    def cpu_percent(self, interval=None):
        return next(self._cpu)


class VanishingProc(FakeProc):
    def cpu_percent(self, interval=None):
        raise psutil.NoSuchProcess(self.pid)


@pytest.fixture
def fake_system(monkeypatch):
    procs: list = []
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: list(procs))
    monkeypatch.setattr(psutil, "cpu_count", lambda logical=True: 4)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    return procs


def test_agrupa_por_nombre_y_ordena_por_memoria(fake_system):
    fake_system += [
        FakeProc(1, "chrome.exe", 500),
        FakeProc(2, "chrome.exe", 700),
        FakeProc(3, "code.exe", 800),
    ]

    groups = top_processes("memory")

    assert [group.name for group in groups] == ["chrome.exe", "code.exe"]
    assert groups[0].count == 2
    assert groups[0].memory_mb == 1200


def test_respeta_el_limite(fake_system):
    fake_system += [FakeProc(1, "a.exe", 10), FakeProc(2, "b.exe", 20)]
    assert len(top_processes("memory", limit=1)) == 1


def test_ordena_por_cpu_normalizada_por_nucleos(fake_system):
    fake_system += [
        FakeProc(1, "a.exe", 10, cpu=(0.0, 80.0)),
        FakeProc(2, "b.exe", 10, cpu=(0.0, 40.0)),
    ]

    groups = top_processes("cpu")

    assert [group.name for group in groups] == ["a.exe", "b.exe"]
    assert groups[0].cpu_percent == 20.0
    assert groups[1].cpu_percent == 10.0


def test_ignora_el_proceso_idle(fake_system):
    fake_system += [
        FakeProc(0, "System Idle Process", 0, cpu=(0.0, 400.0)),
        FakeProc(1, "a.exe", 10, cpu=(0.0, 4.0)),
    ]
    assert [group.name for group in top_processes("cpu")] == ["a.exe"]


def test_tolera_procesos_sin_datos_de_memoria(fake_system):
    fake_system.append(FakeProc(1, "protegido.exe", None))
    assert top_processes("memory")[0].memory_mb == 0.0


def test_un_proceso_que_desaparece_a_mitad_de_la_medicion_no_rompe_nada(fake_system):
    fake_system.append(VanishingProc(1, "efimero.exe", 10))
    groups = top_processes("cpu")
    assert groups[0].cpu_percent == 0.0


def test_format_processes_por_memoria():
    groups = [
        ProcessGroup("chrome.exe", 24, 3276.8, 0.0),
        ProcessGroup("code.exe", 1, 512.0, 0.0),
    ]
    text = format_processes(groups, "memory")
    assert "1. chrome.exe (24 procesos): 3.2 GB" in text
    assert "2. code.exe: 512 MB" in text


def test_format_processes_por_cpu():
    text = format_processes([ProcessGroup("a.exe", 1, 10.0, 12.34)], "cpu")
    assert "1. a.exe: 12.3% de CPU" in text


def test_format_processes_vacio():
    assert "No pude leer" in format_processes([])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("cpu", "cpu"),
        ("Procesador", "cpu"),
        ("memoria", "memory"),
        ("RAM", "memory"),
        ("", "memory"),
        ("lo que sea", "memory"),
    ],
)
def test_normalize_sort(text, expected):
    assert normalize_sort(text) == expected