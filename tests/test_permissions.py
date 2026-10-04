"""Pruebas del sistema de permisos."""
import pytest

from core.permissions import (
    PERMISSIONS_FILE,
    PermissionConfigError,
    PermissionPolicy,
    load_policy,
)
from core.tool_registry import RiskLevel, Tool
from pathlib import Path
from core import paths


def make_tool(name: str = "tool", risk: RiskLevel = RiskLevel.SAFE) -> Tool:
    return Tool(name=name, description="prueba", risk=risk, func=lambda **kwargs: None)


@pytest.fixture
def policy() -> PermissionPolicy:
    return PermissionPolicy.from_dict(
        {
            "protected_paths": ["C:\\Windows"],
            "protected_processes": ["explorer", "python"],
            "blocked_command_patterns": ["\\bformat\\s+[a-z]:"],
            "confirm_command_patterns": ["\\bRemove-Item\\b"],
        }
    )


def test_herramienta_segura_se_permite(policy):
    result = policy.check(make_tool(), {})
    assert result.allowed
    assert result.risk is RiskLevel.SAFE


def test_confirmacion_requerida(policy):
    tool = make_tool(risk=RiskLevel.CONFIRMATION_REQUIRED)
    assert policy.check(tool, {}).needs_confirmation
    assert policy.check(tool, {}, confirmed=True).allowed


def test_bloqueada_no_se_desbloquea_ni_confirmando(policy):
    result = policy.check(make_tool(risk=RiskLevel.BLOCKED), {}, confirmed=True)
    assert not result.allowed
    assert result.risk is RiskLevel.BLOCKED


@pytest.mark.parametrize(
    "path", ["C:\\Windows\\System32\\config.txt", "C:\\Users\\..\\Windows\\x.txt"]
)
def test_ruta_protegida_exige_confirmacion(policy, path):
    assert policy.check(make_tool(), {"path": path}).needs_confirmation


def test_ruta_normal_sigue_siendo_segura(policy, tmp_path):
    assert policy.check(make_tool(), {"path": str(tmp_path / "pruebas")}).allowed


def test_proceso_protegido(policy):
    assert policy.check(make_tool(), {"app": "Explorer.EXE"}).needs_confirmation
    assert policy.check(make_tool(), {"app": "spotify"}).allowed


@pytest.mark.parametrize(
    ("command", "risk"),
    [
        ("Get-Process | Format-Table", RiskLevel.SAFE),
        ("Remove-Item prueba.txt", RiskLevel.CONFIRMATION_REQUIRED),
        ("format C:", RiskLevel.BLOCKED),
        ("Remove-Item a.txt; format D:", RiskLevel.BLOCKED),
    ],
)
def test_reglas_de_comandos(policy, command, risk):
    assert policy.check(make_tool(), {"command": command}).risk is risk


def test_override_solo_puede_endurecer():
    policy = PermissionPolicy.from_dict(
        {"tool_overrides": {"a": "confirmation_required", "b": "safe"}}
    )
    assert policy.check(make_tool("a"), {}).needs_confirmation
    tool_b = make_tool("b", RiskLevel.CONFIRMATION_REQUIRED)
    assert policy.check(tool_b, {}).risk is RiskLevel.CONFIRMATION_REQUIRED


@pytest.mark.parametrize(
    "data",
    [
        {"blocked_command_patterns": ["(sin cerrar"]},
        {"tool_overrides": {"x": "inventado"}},
    ],
)
def test_configuracion_invalida_lanza_error(data):
    with pytest.raises(PermissionConfigError):
        PermissionPolicy.from_dict(data)


def test_load_policy_lee_el_archivo_real():
    policy = load_policy(PERMISSIONS_FILE)
    assert policy.check(make_tool(), {"command": "format C:"}).risk is RiskLevel.BLOCKED
    assert policy.check(make_tool(), {"app": "explorer"}).needs_confirmation


def test_load_policy_archivo_inexistente(tmp_path):
    with pytest.raises(PermissionConfigError):
        load_policy(tmp_path / "no_existe.json")

def test_rutas_fuera_de_las_carpetas_permitidas_piden_confirmacion(tmp_path):
    policy = PermissionPolicy.from_dict({"allowed_roots": [str(tmp_path)]})
    assert policy.check(make_tool(), {"path": str(tmp_path / "a.txt")}).allowed
    outside = tmp_path.parent / "otra" / "a.txt"
    assert policy.check(make_tool(), {"path": str(outside)}).needs_confirmation


def test_las_variables_de_entorno_se_expanden_en_las_rutas_protegidas(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_DIR", str(tmp_path))
    policy = PermissionPolicy.from_dict({"protected_paths": ["%JARVIS_TEST_DIR%\\secreto"]})
    secret = tmp_path / "secreto" / "a.txt"
    assert policy.check(make_tool(), {"path": str(secret)}).needs_confirmation


def test_las_rutas_relativas_se_evaluan_como_las_resuelven_las_herramientas(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "default_dir", lambda: tmp_path)
    policy = PermissionPolicy.from_dict({"protected_paths": [str(tmp_path / "secreto")]})
    assert policy.check(make_tool(), {"path": "secreto/a.txt"}).needs_confirmation
    assert policy.check(make_tool(), {"path": "libre/a.txt"}).allowed


def test_el_archivo_real_protege_appdata_y_lo_que_esta_fuera_del_usuario():
    policy = load_policy(PERMISSIONS_FILE)
    home = Path.home()
    assert policy.check(make_tool(), {"path": str(home / "AppData" / "x")}).needs_confirmation
    assert policy.check(make_tool(), {"path": "C:\\Temp\\x.txt"}).needs_confirmation
    assert policy.check(make_tool(), {"path": str(home / "Documents" / "x.txt")}).allowed