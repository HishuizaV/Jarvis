"""Pruebas del Intent Router con un cliente falso (no necesitan Ollama)."""
import pytest

from core.intent_router import (
    ACTION_CLAIM_WARNING,
    CHAT_PROMPT,
    SYSTEM_PROMPT,
    Intent,
    IntentRouter,
    ToolCall,
    claims_action,
    mentions_files,
    needs_tools,
)

from core.tool_registry import GROUP_FILES, RiskLevel, ToolParameter, ToolRegistry

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


def test_route_con_herramientas_no_envia_historial(reg):
    client = FakeClient({"role": "assistant", "content": "ok"})
    history = [
        {"role": "user", "content": "antes"},
        {"role": "assistant", "content": "respuesta"},
    ]
    IntentRouter(client, reg).route("crea una carpeta", history=history)

    call = client.calls[0]
    assert call["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "crea una carpeta"},
    ]
    assert call["temperature"] == 0.0
    assert call["tools"][0]["function"]["name"] == "create_folder"


def test_route_de_conversacion_si_envia_historial_y_ninguna_herramienta(reg):
    client = FakeClient({"role": "assistant", "content": "ok"})
    history = [
        {"role": "user", "content": "antes"},
        {"role": "assistant", "content": "respuesta"},
    ]
    IntentRouter(client, reg).route("ahora", history=history)

    call = client.calls[0]
    assert call["messages"][1:3] == history
    assert call["messages"][-1] == {"role": "user", "content": "ahora"}
    assert call["tools"] is None

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
        ("Bloquea la pantalla", True),
        ("¿Qué sistema operativo tengo?", True),
        ("¿Está Spotify abierto?", True),
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

@pytest.fixture
def reg2() -> ToolRegistry:
    r = ToolRegistry()

    @r.register(
        name="open_file",
        description="Abre un archivo.",
        risk=RiskLevel.SAFE,
        group=GROUP_FILES,
        parameters=[ToolParameter("path", "string", "Ruta")],
    )
    def open_file(path: str) -> str:
        return path

    @r.register(
        name="open_app",
        description="Abre una aplicación.",
        risk=RiskLevel.SAFE,
        parameters=[ToolParameter("app", "string", "Nombre")],
    )
    def open_app(app: str) -> str:
        return app

    return r


def test_si_el_mensaje_habla_de_archivos_solo_se_ofrecen_las_de_archivos(reg2):
    client = FakeClient({"role": "assistant", "content": ""})
    IntentRouter(client, reg2).route("abre script.bat")
    names = [tool["function"]["name"] for tool in client.calls[0]["tools"]]
    assert names == ["open_file"]


def test_si_no_habla_de_archivos_se_ofrecen_todas(reg2):
    client = FakeClient({"role": "assistant", "content": ""})
    IntentRouter(client, reg2).route("abre spotify")
    names = [tool["function"]["name"] for tool in client.calls[0]["tools"]]
    assert names == ["open_file", "open_app"]


def test_si_no_hay_herramientas_de_archivos_se_ofrecen_todas(reg):
    client = FakeClient({"role": "assistant", "content": ""})
    IntentRouter(client, reg).route("crea un archivo notas.txt")
    assert client.calls[0]["tools"][0]["function"]["name"] == "create_folder"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Abre script.bat", True),
        ("Abre notas.txt", True),
        ("Crea una carpeta llamada fotos", True),
        ("Busca el archivo notas", True),
        ("Abre Spotify", False),
        ("Abre python 3.12", False),
    ],
)
def test_mentions_files(texto, esperado):
    assert mentions_files(texto) is esperado

@pytest.mark.parametrize(
    ("respuesta", "esperado"),
    [
        ("Abrí C:\\Users\\Holcen\\notas.txt", True),
        ('Escribió "hola" en el archivo notas.txt', True),
        ("He creado la carpeta fotos.", True),
        ("Para abrir un archivo usa open().", False),
        ("Python es un lenguaje de programación.", False),
        ("La capital de Francia es París.", False),
        ("Para ejecutar el script, ejecute python main.py.", False),
    ],
)
def test_claims_action(respuesta, esperado):
    assert claims_action(respuesta) is esperado


def test_en_conversacion_una_respuesta_que_afirma_haber_hecho_algo_se_reemplaza(reg):
    client = FakeClient({"role": "assistant", "content": "Abrí el archivo notas.txt"})
    intent = IntentRouter(client, reg).route("la ruta de jarvis_pruebas")
    assert intent.tool_call is None
    assert intent.reply == ACTION_CLAIM_WARNING


def test_en_conversacion_se_usa_el_prompt_que_dice_que_no_hay_acciones(reg):
    client = FakeClient({"role": "assistant", "content": "Hola"})
    IntentRouter(client, reg).route("hola")
    assert client.calls[0]["messages"][0] == {"role": "system", "content": CHAT_PROMPT}