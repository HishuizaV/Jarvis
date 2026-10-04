"""Pruebas del control de aplicaciones (sin abrir ni cerrar nada real)."""
import os
import subprocess
from types import SimpleNamespace

import psutil
import pytest

import tools.apps as apps
from core.permissions import load_policy
from services.installed_apps import InstalledApp, SearchResult
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


class FakeIndex:
    """Imita al índice de apps instaladas (así los tests no ejecutan PowerShell)."""

    def __init__(self) -> None:
        self.result = SearchResult("none")
        self.queries: list[str] = []

    def search(self, query: str) -> SearchResult:
        self.queries.append(query)
        return self.result


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    cat = AppCatalog.from_dict(DATA)
    monkeypatch.setattr(apps, "get_catalog", lambda: cat)
    return cat


@pytest.fixture(autouse=True)
def index(monkeypatch):
    fake = FakeIndex()
    monkeypatch.setattr(apps, "get_index", lambda: fake)
    return fake


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


def test_open_app_del_catalogo_no_consulta_las_apps_instaladas(monkeypatch, index):
    monkeypatch.setattr(os, "startfile", lambda target: None, raising=False)
    open_app("spotify")
    assert index.queries == []


def test_open_app_desconocida_no_lanza_nada(monkeypatch):
    launched = []
    monkeypatch.setattr(os, "startfile", launched.append, raising=False)
    assert "No encontré" in open_app("malware.exe")
    assert launched == []


def test_open_app_usa_las_apps_instaladas_si_no_esta_en_el_catalogo(monkeypatch, index):
    launched = []
    monkeypatch.setattr(os, "startfile", launched.append, raising=False)
    index.result = SearchResult("match", (InstalledApp("Adobe Photoshop 2025", "photoshop.id"),))

    assert "Adobe Photoshop 2025" in open_app("photoshop")
    assert launched == ["shell:AppsFolder\\photoshop.id"]
    assert index.queries == ["photoshop"]


def test_open_app_ambigua_lista_las_opciones_y_no_abre(monkeypatch, index):
    launched = []
    monkeypatch.setattr(os, "startfile", launched.append, raising=False)
    index.result = SearchResult(
        "ambiguous",
        (InstalledApp("Visual Studio 2022", "a"), InstalledApp("Visual Studio Code", "b")),
    )

    answer = open_app("visual studio")

    assert "Visual Studio 2022" in answer
    assert "Visual Studio Code" in answer
    assert launched == []


def test_open_app_con_sugerencia_pide_confirmar_sin_abrir(monkeypatch, index):
    launched = []
    monkeypatch.setattr(os, "startfile", launched.append, raising=False)
    index.result = SearchResult("suggestion", (InstalledApp("Visual Studio Code", "b"),))

    assert "¿Quisiste decir" in open_app("visual studio kode")
    assert launched == []


def test_open_app_sin_lista_de_apps_avisa(index):
    index.result = SearchResult("unavailable")
    assert "No pude consultar" in open_app("photoshop")


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


@pytest.mark.parametrize("data", [{"x": {"launch": "x"}}, {"x": "no es un objeto"}])
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


def test_el_catalogo_real_distingue_terminal_powershell_y_cmd():
    catalog = AppCatalog.from_file(apps.APPS_FILE)
    assert catalog.find("terminal").process == "WindowsTerminal.exe"
    assert catalog.find("powershell").process == "powershell.exe"
    assert catalog.find("cmd").process == "cmd.exe"