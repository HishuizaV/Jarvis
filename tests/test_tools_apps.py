"""Pruebas del control de aplicaciones (sin abrir ni cerrar nada real)."""
import os
import subprocess
from types import SimpleNamespace

import psutil
import pytest

import tools.apps as apps
from core.permissions import load_policy
from tools.apps import AppCatalog, AppConfigError, close_app, is_app_running, open_app

DATA = {
    "spotify": {"aliases": ["spotify"], "launch": "spotify:", "process": "Spotify.exe"},
    "vscode": {"aliases": ["vs code", "code"], "launch": "code", "process": "Code.exe"},
    "calculadora": {
        "aliases": ["calc"],
        "launch": "calc",
        "process": "CalculatorApp.exe",
        "force_close": True,
    },
    "terminal": {
        "aliases": ["powershell"],
        "launch": "wt",
        "process": "WindowsTerminal.exe",
        "can_close": False,
    },
}


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    cat = AppCatalog.from_dict(DATA)
    monkeypatch.setattr(apps, "get_catalog", lambda: cat)
    return cat


def fake_taskkill(returncode: int, calls: list):
    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=returncode, stderr="")

    return fake_run


def test_find_ignora_mayusculas_espacios_y_exe(catalog):
    assert catalog.find("  VS Code ").name == "vscode"
    assert catalog.find("spotify.exe").name == "spotify"
    assert catalog.find("photoshop") is None


def test_open_app_lanza_la_aplicacion(monkeypatch):
    launched = []
    monkeypatch.setattr(os, "startfile", launched.append, raising=False)
    assert "Abriendo" in open_app("Spotify")
    assert launched == ["spotify:"]


def test_open_app_desconocida_no_lanza_nada(monkeypatch):
    launched = []
    monkeypatch.setattr(os, "startfile", launched.append, raising=False)
    assert "No conozco" in open_app("malware.exe")
    assert launched == []


def test_open_app_avisa_si_windows_no_la_encuentra(monkeypatch):
    def fail(target):
        raise FileNotFoundError("no encontrado")

    monkeypatch.setattr(os, "startfile", fail, raising=False)
    assert "No pude abrir" in open_app("vscode")


def test_close_app_pide_cierre_suave(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", fake_taskkill(0, calls))
    assert "se cierre" in close_app("spotify")
    assert calls == [["taskkill", "/IM", "Spotify.exe"]]


def test_close_app_fuerza_solo_si_el_catalogo_lo_indica(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", fake_taskkill(0, calls))
    close_app("calculadora")
    assert calls == [["taskkill", "/IM", "CalculatorApp.exe", "/F"]]


def test_close_app_que_no_esta_abierta(monkeypatch):
    monkeypatch.setattr(subprocess, "run", fake_taskkill(128, []))
    assert "no está en ejecución" in close_app("spotify")


def test_close_app_no_cierra_apps_marcadas_como_no_cerrables(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", fake_taskkill(0, calls))
    assert "Por seguridad" in close_app("terminal")
    assert calls == []


def test_is_app_running_detecta_el_proceso(monkeypatch):
    fake = [SimpleNamespace(info={"name": "spotify.EXE"}), SimpleNamespace(info={"name": None})]
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: fake)
    assert "está en ejecución" in is_app_running("spotify")


def test_is_app_running_cuando_no_esta(monkeypatch):
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: [])
    assert "no está en ejecución" in is_app_running("spotify")


@pytest.mark.parametrize(
    "data", [{"x": {"launch": "x"}}, {"x": "no es un objeto"}]
)
def test_catalogo_invalido_lanza_error(data):
    with pytest.raises(AppConfigError):
        AppCatalog.from_dict(data)


def test_el_catalogo_real_es_valido_y_no_expone_procesos_protegidos():
    catalog = AppCatalog.from_file(apps.APPS_FILE)
    protected = load_policy().protected_processes
    for entry in catalog.entries():
        assert entry.launch
        if entry.can_close:
            assert entry.process.lower().removesuffix(".exe") not in protected