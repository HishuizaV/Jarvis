"""Pruebas de las herramientas de archivos (en una carpeta temporal, sin tocar tus archivos)."""
import os
from pathlib import Path

import pytest

from core import paths
from core.tool_registry import RiskLevel, registry
from tools import load_tools
from tools.files import copy_file, create_folder, find_file, move_file, open_file, rename_file


@pytest.fixture
def work(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "trabajo"
    folder.mkdir()
    monkeypatch.setattr(paths, "default_dir", lambda: folder)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    return folder.resolve()


@pytest.fixture
def opened(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(os, "startfile", calls.append, raising=False)
    return calls


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- create_folder ---------------------------------------------------------

def test_create_folder_crea_la_carpeta_en_la_carpeta_base(work):
    assert "Carpeta creada" in create_folder("fotos")
    assert (work / "fotos").is_dir()


def test_create_folder_existente_avisa(work):
    (work / "fotos").mkdir()
    assert "ya existe" in create_folder("fotos")


def test_create_folder_no_pisa_un_archivo(work):
    write(work / "fotos")
    assert "Ya existe un archivo" in create_folder("fotos")


# --- find_file -------------------------------------------------------------

def test_find_file_encuentra_por_nombre_parcial(work):
    target = write(work / "docs" / "Notas importantes.txt")
    write(work / "otra.txt")

    result = find_file("notas")

    assert str(target) in result
    assert "1 resultado" in result


def test_find_file_sin_resultados(work):
    assert "No encontré" in find_file("inexistente")


def test_find_file_ignora_carpetas_tecnicas(work):
    write(work / "node_modules" / "notas.txt")
    assert "No encontré" in find_file("notas")


def test_find_file_en_una_carpeta_indicada(work):
    write(work / "a" / "plan.txt")
    write(work / "b" / "plan.txt")
    assert "1 resultado" in find_file("plan", folder="a")


# --- open_file -------------------------------------------------------------

def test_open_file_abre_un_archivo(work, opened):
    target = write(work / "notas.txt")
    assert "Abriendo" in open_file("notas.txt")
    assert opened == [target]


def test_open_file_busca_por_nombre_parcial(work, opened):
    target = write(work / "docs" / "notas.txt")
    open_file("notas")
    assert opened == [target]


def test_open_file_con_varias_coincidencias_no_abre(work, opened):
    write(work / "notas1.txt")
    write(work / "notas2.txt")
    assert "varios" in open_file("notas")
    assert opened == []


def test_open_file_no_abre_ejecutables(work, opened):
    write(work / "script.bat")
    assert "Por seguridad" in open_file("script.bat")
    assert opened == []


def test_open_file_inexistente(work, opened):
    assert "No encontré" in open_file("fantasma.txt")
    assert opened == []


# --- copy_file -------------------------------------------------------------

def test_copy_file_copia_con_nuevo_nombre(work):
    write(work / "a.txt", "hola")
    assert "Copiado" in copy_file("a.txt", "b.txt")
    assert (work / "b.txt").read_text(encoding="utf-8") == "hola"
    assert (work / "a.txt").exists()


def test_copy_file_dentro_de_una_carpeta_existente(work):
    write(work / "a.txt")
    (work / "fotos").mkdir()
    copy_file("a.txt", "fotos")
    assert (work / "fotos" / "a.txt").exists()


def test_copy_file_no_sobrescribe(work):
    write(work / "a.txt", "nuevo")
    write(work / "b.txt", "viejo")
    assert "Ya existe" in copy_file("a.txt", "b.txt")
    assert (work / "b.txt").read_text(encoding="utf-8") == "viejo"


def test_copy_file_copia_carpetas_completas(work):
    write(work / "proyecto" / "x.txt", "1")
    copy_file("proyecto", "respaldo")
    assert (work / "respaldo" / "x.txt").exists()


def test_copy_file_no_copia_una_carpeta_dentro_de_si_misma(work):
    (work / "proyecto").mkdir()
    assert "dentro de sí misma" in copy_file("proyecto", "proyecto/sub")


# --- move_file -------------------------------------------------------------

def test_move_file_mueve_el_archivo(work):
    write(work / "a.txt")
    (work / "fotos").mkdir()
    assert "Movido" in move_file("a.txt", "fotos")
    assert not (work / "a.txt").exists()
    assert (work / "fotos" / "a.txt").exists()


def test_move_file_no_sobrescribe(work):
    write(work / "a.txt", "nuevo")
    write(work / "fotos" / "a.txt", "viejo")
    assert "Ya existe" in move_file("a.txt", "fotos")
    assert (work / "fotos" / "a.txt").read_text(encoding="utf-8") == "viejo"
    assert (work / "a.txt").exists()


def test_move_y_rename_rechazan_carpetas_principales(work):
    assert "Por seguridad" in move_file(str(work), "otra")
    assert "Por seguridad" in rename_file(str(work), "otra")


# --- rename_file -----------------------------------------------------------

def test_rename_file_cambia_el_nombre(work):
    write(work / "a.txt")
    assert "Renombrado" in rename_file("a.txt", "b.txt")
    assert (work / "b.txt").exists()
    assert not (work / "a.txt").exists()


def test_rename_file_rechaza_nombres_invalidos(work):
    write(work / "a.txt")
    assert "no es válido" in rename_file("a.txt", "sub/b.txt")
    assert (work / "a.txt").exists()


def test_rename_file_no_sobrescribe(work):
    write(work / "a.txt")
    write(work / "b.txt")
    assert "Ya existe" in rename_file("a.txt", "b.txt")


# --- registro --------------------------------------------------------------

def test_las_herramientas_de_archivos_estan_registradas_como_seguras():
    load_tools()
    for name in ("create_folder", "find_file", "open_file", "copy_file", "move_file", "rename_file"):
        assert registry.get(name).risk is RiskLevel.SAFE