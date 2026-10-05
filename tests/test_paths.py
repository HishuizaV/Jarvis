"""Pruebas de la resolución de rutas."""
import os
from pathlib import Path

import pytest

from core import paths
from core.paths import candidate_paths, is_root_folder, resolve_existing, resolve_user_path


def test_una_ruta_relativa_va_a_la_carpeta_base(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "default_dir", lambda: tmp_path)
    assert resolve_user_path("pruebas") == (tmp_path / "pruebas").resolve()


def test_un_nombre_de_carpeta_conocida_va_al_perfil_de_usuario(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert resolve_user_path("Descargas/x.txt") == (tmp_path / "Downloads" / "x.txt").resolve()


def test_una_ruta_absoluta_se_normaliza(tmp_path):
    messy = tmp_path / "a" / ".." / "b"
    assert resolve_user_path(str(messy)) == (tmp_path / "b").resolve()


def test_las_variables_de_entorno_se_expanden(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_T", str(tmp_path))
    assert resolve_user_path("%JARVIS_T%\\x") == (tmp_path / "x").resolve()


def test_una_ruta_vacia_es_invalida():
    with pytest.raises(ValueError):
        resolve_user_path("   ")


@pytest.mark.skipif(os.name != "nt", reason="rutas con unidad: solo Windows")
def test_una_ruta_con_unidad_pero_sin_ubicacion_es_invalida():
    with pytest.raises(ValueError):
        resolve_user_path("C:notas.txt")


def test_is_root_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(paths, "default_dir", lambda: tmp_path / "Documents")

    assert is_root_folder(tmp_path.resolve())
    assert is_root_folder((tmp_path / "Downloads").resolve())
    assert is_root_folder((tmp_path / "Documents").resolve())
    assert is_root_folder(Path(Path.cwd().anchor))
    assert not is_root_folder((tmp_path / "Downloads" / "x").resolve())

def test_un_nombre_comun_que_no_es_carpeta_de_windows_va_a_la_carpeta_base(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "default_dir", lambda: tmp_path)
    assert resolve_user_path("fotos") == (tmp_path / "fotos").resolve()

def test_una_barra_inicial_se_trata_como_relativa(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert resolve_user_path("\\Descargas") == (tmp_path / "Downloads").resolve()
    assert resolve_user_path("/descargas/x.txt") == (tmp_path / "Downloads" / "x.txt").resolve()


def test_candidate_paths_prueba_la_base_y_las_carpetas_del_usuario(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(paths, "default_dir", lambda: tmp_path / "base")

    assert candidate_paths("x.txt") == [
        (tmp_path / "base" / "x.txt").resolve(),
        (home / "Documents" / "x.txt").resolve(),
        (home / "Desktop" / "x.txt").resolve(),
        (home / "Downloads" / "x.txt").resolve(),
    ]


def test_resolve_existing_prefiere_la_ruta_que_existe(tmp_path, monkeypatch):
    home = tmp_path / "home"
    sandbox = home / "Documents" / "jarvis_pruebas"
    sandbox.mkdir(parents=True)
    (sandbox / "notas.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(paths, "default_dir", lambda: sandbox)

    # La carpeta base YA es jarvis_pruebas: 'jarvis_pruebas/notas.txt' no debe duplicar el nombre.
    assert resolve_existing("jarvis_pruebas/notas.txt") == (sandbox / "notas.txt").resolve()


def test_resolve_existing_sin_coincidencias_usa_la_preferida(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(paths, "default_dir", lambda: tmp_path / "base")
    assert resolve_existing("nada.txt") == (tmp_path / "base" / "nada.txt").resolve()