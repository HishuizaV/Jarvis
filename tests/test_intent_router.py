"""Pruebas del Intent Router con un cliente falso (no necesitan Ollama)."""
import pytest

from core.intent_router import SYSTEM_PROMPT, Intent, IntentRouter, ToolCall, needs_tools
from core.tool_registry import RiskLevel, ToolParameter, ToolRegistry


class FakeClient:
    """Imita a OllamaClient: devuelve un mensaje fijo y recuerda cómo lo llamaron."""

    def __init__(self, message: dict) -> None:
        self.message = message
        self.calls: list[dict] = []

    def chat(self, messages, tools=None, json_mode=False, temperature=None):
        self.calls.append({"messages": messages, "tools": tools, "temperature": temperature})
        return self.message


@pytest.fixture
def reg() -> ToolRegistry:
    r = ToolRegistry()

    @r.register(
        name="create_folder",
        description="Crea una carpeta.",
        risk=RiskLevel.SAFE,
        parameters=[ToolParameter("name", "string", "Nombre")],
    )
    def create_folder(name: str) -> str:
        return name

    return r


def test_mensaje_con_herramienta_se_convierte_en_tool_call(reg):
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "create_folder", "arguments": {"name": "pruebas"}}}],
    }
    intent = IntentRouter(FakeClient(message), reg).route("crea una carpeta pruebas")
    assert intent == Intent(tool_call=ToolCall("create_folder", {"name": "pruebas"}))


def test_mensaje_de_texto_es_solo_conversacion(reg):
    client = FakeClient({"role": "assistant", "content": " ¡Hola! "})
    intent = IntentRouter(client, reg).route("hola")
    assert intent.tool_call is None
    assert intent.reply == "¡Hola!"


def test_herramienta_inexistente_se_rechaza(reg):
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "hackear_nasa", "arguments": {}}}],
    }
    intent = IntentRouter(FakeClient(message), reg).route("abre algo")
    assert intent.tool_call is None
    assert intent.reply


def test_route_envia_prompt_historial_temperatura_y_herramientas(reg):
    client = FakeClient({"role": "assistant", "content": "ok"})
    history = [
        {"role": "user", "content": "antes"},
        {"role": "assistant", "content": "respuesta"},
    ]
    IntentRouter(client, reg).route("crea una carpeta", history=history)

    call = client.calls[0]
    assert call["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert call["messages"][1:3] == history
    assert call["messages"][-1] == {"role": "user", "content": "crea una carpeta"}
    assert call["temperature"] == 0.0
    assert call["tools"][0]["function"]["name"] == "create_folder"

@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Abre Spotify", True),
        ("¿Cuánta RAM estoy usando?", True),
        ("¿Qué hora es?", True),
        ("Crea una carpeta llamada pruebas", True),
        ("Recuérdame esto en 30 minutos", True),
        ("Hola, ¿cómo estás?", False),
        ("¿Cuál es la capital de Francia?", False),
        ("Explícame qué es una variable en Python", False),
    ],
)
def test_needs_tools(texto, esperado):
    assert needs_tools(texto) is esperado


def test_sin_palabras_de_accion_no_se_ofrecen_ni_aceptan_herramientas(reg):
    message = {
        "role": "assistant",
        "content": "Hola",
        "tool_calls": [{"function": {"name": "create_folder", "arguments": {"name": "x"}}}],
    }
    client = FakeClient(message)
    intent = IntentRouter(client, reg).route("Hola, ¿cómo estás?")

    assert client.calls[0]["tools"] is None
    assert intent.tool_call is None
    assert intent.reply == "Hola"