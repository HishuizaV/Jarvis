"""Pruebas del descubrimiento de apps instaladas (sin ejecutar PowerShell real)."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from services.installed_apps import (
    InstalledApp,
    InstalledApps,
    find_matches,
    parse_start_apps,
    query_start_apps,
)

RAW = json.dumps(
    [
        {"Name": "Calculadora", "AppID": "calc.id"},
        {"Name": "Spotify", "AppID": "spotify.id"},
    ]
)

APPS = [
    InstalledApp("Calculadora", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
    InstalledApp("Adobe Photoshop 2025", "{GUID}\\Adobe\\Photoshop.exe"),
    InstalledApp("Visual Studio Code", "Microsoft.VisualStudioCode"),
    InstalledApp("Visual Studio 2022", "{GUID}\\VS\\devenv.exe"),
]


def test_parse_lee_una_lista():
    assert [app.name for app in parse_start_apps(RAW)] == ["Calculadora", "Spotify"]


def test_parse_acepta_un_solo_objeto():
    apps = parse_start_apps(json.dumps({"Name": "Solo", "AppID": "solo.id"}))
    assert [app.name for app in apps] == ["Solo"]


def test_parse_quita_duplicados():
    raw = json.dumps(
        [{"Name": "Spotify", "AppID": "a"}, {"Name": "spotify", "AppID": "b"}]
    )
    assert len(parse_start_apps(raw)) == 1


def test_parse_quita_desinstaladores():
    raw = json.dumps(
        [
            {"Name": "Uninstall Foo", "AppID": "a"},
            {"Name": "Desinstalar Foo", "AppID": "b"},
            {"Name": "Foo", "AppID": "c"},
        ]
    )
    assert [app.name for app in parse_start_apps(raw)] == ["Foo"]


@pytest.mark.parametrize("raw", ["", "esto no es json"])
def test_parse_con_salida_invalida_devuelve_lista_vacia(raw):
    assert parse_start_apps(raw) == []


def test_query_start_apps_ejecuta_get_startapps_sin_shell(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=RAW, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert [app.name for app in query_start_apps()] == ["Calculadora", "Spotify"]
    assert calls[0][0] == "powershell"
    assert "Get-StartApps" in calls[0][-1]


def test_query_start_apps_con_error_devuelve_lista_vacia(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda args, **kw: SimpleNamespace(returncode=1, stdout="", stderr="boom")
    )
    assert query_start_apps() == []


def test_query_start_apps_con_timeout_devuelve_lista_vacia(monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert query_start_apps() == []


@pytest.mark.parametrize(
    ("query", "kind", "first"),
    [
        ("Calculadora", "match", "Calculadora"),
        ("CALCULADORA", "match", "Calculadora"),
        ("photoshop", "match", "Adobe Photoshop 2025"),
        ("visual studio", "ambiguous", None),
        ("visual studio kode", "suggestion", "Visual Studio Code"),
        ("zzzz", "none", None),
        ("ab", "none", None),
    ],
)
def test_find_matches(query, kind, first):
    result = find_matches(query, APPS)
    assert result.kind == kind
    if first is not None:
        assert result.apps[0].name == first


def make_index(tmp_path, apps, calls, clock):
    def loader():
        calls.append(1)
        return apps

    return InstalledApps(
        cache_file=tmp_path / "cache.json", loader=loader, now=lambda: clock["t"]
    )


def test_la_primera_busqueda_carga_y_guarda_la_cache(tmp_path):
    calls, clock = [], {"t": 1000.0}
    index = make_index(tmp_path, APPS, calls, clock)

    assert index.search("calculadora").kind == "match"
    assert index.search("calculadora").kind == "match"

    assert len(calls) == 1
    assert (tmp_path / "cache.json").exists()


def test_otra_instancia_usa_la_cache_sin_consultar_a_windows(tmp_path):
    calls, clock = [], {"t": 1000.0}
    make_index(tmp_path, APPS, calls, clock).search("calculadora")
    calls.clear()

    assert make_index(tmp_path, APPS, calls, clock).search("photoshop").kind == "match"
    assert calls == []


def test_cache_vencida_se_vuelve_a_consultar(tmp_path):
    calls, clock = [], {"t": 1000.0}
    make_index(tmp_path, APPS, calls, clock).search("calculadora")
    calls.clear()

    clock["t"] += 25 * 3600
    make_index(tmp_path, APPS, calls, clock).search("calculadora")
    assert calls == [1]


def test_si_no_encuentra_reconsulta_pero_con_limite_de_frecuencia(tmp_path):
    calls, clock = [], {"t": 1000.0}
    index = make_index(tmp_path, APPS, calls, clock)

    assert index.search("zzzz").kind == "none"
    clock["t"] = 1010.0
    assert index.search("zzzz").kind == "none"
    assert len(calls) == 1  # demasiado pronto para reconsultar

    clock["t"] = 1400.0
    assert index.search("zzzz").kind == "none"
    assert len(calls) == 2


def test_sin_lista_de_apps_el_resultado_es_unavailable_y_no_escribe_cache(tmp_path):
    calls, clock = [], {"t": 1000.0}
    index = make_index(tmp_path, [], calls, clock)

    assert index.search("calculadora").kind == "unavailable"
    assert not (tmp_path / "cache.json").exists()


def test_cache_corrupta_se_ignora(tmp_path):
    (tmp_path / "cache.json").write_text("esto no es json", encoding="utf-8")
    calls, clock = [], {"t": 1000.0}

    assert make_index(tmp_path, APPS, calls, clock).search("calculadora").kind == "match"
    assert len(calls) == 1