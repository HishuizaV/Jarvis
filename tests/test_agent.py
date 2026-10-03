"""Pruebas del Agent con un router falso (no necesitan Ollama)."""
import json
import logging

import pytest

from core.agent import Agent, parse_confirmation
from core.intent_router import Intent, ToolCall
from core.ollama_client import OllamaError
from core.permissions import PermissionPolicy
from core.tool_registry import RiskLevel, ToolParameter, ToolRegistry


class FakeRouter:
    """Devuelve intents (o lanza errores) en el orden indicado."""

    def __init__(self, *items) -> None:
        self._items = list(items)
        self.calls: list[str] = []

    def route(self, user_text, history=None):
        self.calls.append(user_text)
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def tool_intent(name: str, **arguments) -> Intent:
    return Intent(tool_call=ToolCall(name, arguments))


@pytest.fixture
def env():
    executed: list[str] = []
    reg = ToolRegistry()

    @reg.register(name="get_time", description="Hora.", risk=RiskLevel.SAFE)
    def get_time() -> str:
        executed.append("get_time")
        return "12:00"

    @reg.register(
        name="create_folder",
        description="Crea una carpeta.",
        risk=RiskLevel.SAFE,
        parameters=[ToolParameter("path", "string", "Ruta")],
    )
    def create_folder(path: str) -> str:
        executed.append(f"create_folder:{path}")
        return f"creada {path}"

    @reg.register(
        name="delete_file",
        description="Borra un archivo.",
        risk=RiskLevel.CONFIRMATION_REQUIRED,
        parameters=[ToolParameter("path", "string", "Ruta")],
    )
    def delete_file(path: str) -> str:
        executed.append(f"delete_file:{path}")
        return f"borrado {path}"

    @reg.register(name="shutdown_pc", description="Apaga.", risk=RiskLevel.BLOCKED)
    def shutdown_pc() -> str:
        executed.append("shutdown_pc")
        return "apagando"

    @reg.register(name="explode", description="Falla.", risk=RiskLevel.SAFE)
    def explode() -> str:
        raise RuntimeError("boom")

    return reg, executed


def make_agent(reg, *items, policy: dict | None = None) -> tuple[Agent, FakeRouter]:
    router = FakeRouter(*items)
    return Agent(router, reg, PermissionPolicy.from_dict(policy or {})), router


def test_conversacion_devuelve_el_texto(env):
    reg, executed = env
    agent, _ = make_agent(reg, Intent(reply="Hola"))
    assert agent.handle("hola") == "Hola"
    assert executed == []


def test_herramienta_segura_se_ejecuta(env):
    reg, executed = env
    agent, _ = make_agent(reg, tool_intent("get_time"))
    assert agent.handle("qué hora es") == "12:00"
    assert executed == ["get_time"]


def test_accion_con_confirmacion_solo_se_ejecuta_tras_el_si(env):
    reg, executed = env
    agent, router = make_agent(reg, tool_intent("delete_file", path="notas.txt"))

    ask = agent.handle("borra notas.txt")
    assert "confirmación" in ask
    assert agent.has_pending
    assert executed == []

    assert agent.handle("sí") == "borrado notas.txt"
    assert executed == ["delete_file:notas.txt"]
    assert not agent.has_pending
    assert len(router.calls) == 1  # el modelo no participó en la confirmación


def test_decir_no_cancela_la_accion(env):
    reg, executed = env
    agent, _ = make_agent(reg, tool_intent("delete_file", path="notas.txt"))
    agent.handle("borra notas.txt")
    assert agent.handle("no") == "De acuerdo, acción cancelada."
    assert executed == []
    assert not agent.has_pending


def test_otro_mensaje_cancela_lo_pendiente_y_se_atiende(env):
    reg, executed = env
    agent, _ = make_agent(
        reg, tool_intent("delete_file", path="notas.txt"), Intent(reply="Estoy bien")
    )
    agent.handle("borra notas.txt")
    assert agent.handle("¿cómo estás?") == "Estoy bien"
    assert executed == []
    assert not agent.has_pending


def test_herramienta_bloqueada_nunca_se_ejecuta(env):
    reg, executed = env
    agent, _ = make_agent(reg, tool_intent("shutdown_pc"))
    assert agent.handle("apaga el equipo").startswith("No puedo hacer eso")
    assert executed == []
    assert not agent.has_pending


def test_argumentos_invalidos_no_piden_confirmacion(env):
    reg, executed = env
    agent, _ = make_agent(reg, tool_intent("delete_file"))
    assert "No pude ejecutar eso" in agent.handle("borra algo")
    assert not agent.has_pending
    assert executed == []


def test_error_en_la_herramienta_no_cierra_el_agente(env):
    reg, _ = env
    agent, _ = make_agent(reg, tool_intent("explode"))
    assert "falló" in agent.handle("explota")


def test_error_de_ollama_da_un_mensaje_claro(env):
    reg, _ = env
    agent, _ = make_agent(reg, OllamaError("sin servidor"))
    assert "modelo" in agent.handle("hola")


def test_ruta_protegida_escala_una_herramienta_segura(env):
    reg, executed = env
    agent, _ = make_agent(
        reg,
        tool_intent("create_folder", path="C:\\Windows\\x"),
        policy={"protected_paths": ["C:\\Windows"]},
    )
    agent.handle("crea una carpeta en C:\\Windows\\x")
    assert agent.has_pending
    assert executed == []


def test_registro_de_auditoria(env, caplog):
    reg, _ = env
    caplog.set_level(logging.INFO, logger="jarvis.audit")
    agent, _ = make_agent(reg, tool_intent("get_time"))
    agent.handle("qué hora es")

    records = [r for r in caplog.records if r.name == "jarvis.audit"]
    record = json.loads(records[-1].getMessage())
    assert record["tool"] == "get_time"
    assert record["decision"] == "executed"
    assert record["request"] == "qué hora es"
    assert isinstance(record["duration_ms"], int)
    assert "ts" in record


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Sí", True),
        ("si, hazlo", True),
        ("confirmo", True),
        ("no", False),
        ("sí pero no", False),
        ("si tuvieras que abrir spotify lo harías", None),
        ("abre spotify", None),
        ("", None),
    ],
)
def test_parse_confirmation(texto, esperado):
    assert parse_confirmation(texto) is esperado