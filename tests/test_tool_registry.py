"""Pruebas del catálogo de herramientas."""
import pytest

from core.tool_registry import RiskLevel, ToolError, ToolParameter, ToolRegistry


@pytest.fixture
def reg() -> ToolRegistry:
    r = ToolRegistry()

    @r.register(
        name="create_folder",
        description="Crea una carpeta.",
        risk=RiskLevel.SAFE,
        parameters=[ToolParameter("name", "string", "Nombre de la carpeta")],
    )
    def create_folder(name: str) -> str:
        return f"creada {name}"

    @r.register(
        name="set_volume",
        description="Cambia el volumen.",
        risk=RiskLevel.SAFE,
        parameters=[ToolParameter("level", "integer", "Volumen de 0 a 100")],
    )
    def set_volume(level: int) -> str:
        return f"volumen {level}"

    @r.register(name="format_disk", description="Peligrosa.", risk=RiskLevel.BLOCKED)
    def format_disk() -> str:
        return "nunca"

    return r


def test_ejecuta_con_argumentos_validos(reg):
    assert reg.get("create_folder").run({"name": "pruebas"}) == "creada pruebas"


def test_herramienta_inexistente(reg):
    with pytest.raises(ToolError):
        reg.get("no_existe")


def test_nombre_duplicado(reg):
    with pytest.raises(ToolError):
        reg.register(name="create_folder", description="x", risk=RiskLevel.SAFE)(lambda: None)


@pytest.mark.parametrize("args", [{}, {"name": "a", "extra": 1}, {"name": 123}])
def test_argumentos_invalidos(reg, args):
    with pytest.raises(ToolError):
        reg.get("create_folder").run(args)


def test_bool_no_cuenta_como_entero(reg):
    with pytest.raises(ToolError):
        reg.get("set_volume").run({"level": True})


def test_esquema_ollama_oculta_las_bloqueadas(reg):
    tools = reg.to_ollama_tools()
    names = [tool["function"]["name"] for tool in tools]
    assert names == ["create_folder", "set_volume"]
    assert tools[0]["function"]["parameters"]["required"] == ["name"]

def test_to_ollama_tools_puede_filtrar_por_grupo():
    r = ToolRegistry()
    r.register(name="a", description="a", risk=RiskLevel.SAFE, group="files")(lambda: None)
    r.register(name="b", description="b", risk=RiskLevel.SAFE)(lambda: None)

    assert [tool["function"]["name"] for tool in r.to_ollama_tools("files")] == ["a"]
    assert len(r.to_ollama_tools()) == 2