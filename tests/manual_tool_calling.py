"""Prueba manual: ¿el modelo local sabe pedir herramientas?

Ejecutar con: python -m tests.manual_tool_calling
"""
import logging
from datetime import datetime

from core.ollama_client import OllamaClient
from core.tool_registry import RiskLevel, ToolError, ToolParameter, ToolRegistry

demo = ToolRegistry()


@demo.register(
    name="get_current_time",
    description="Devuelve la fecha y hora actuales del equipo.",
    risk=RiskLevel.SAFE,
)
def get_current_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


@demo.register(
    name="create_folder",
    description="Crea una carpeta con el nombre indicado.",
    risk=RiskLevel.SAFE,
    parameters=[ToolParameter("name", "string", "Nombre de la carpeta")],
)
def create_folder(name: str) -> str:
    return f"(simulado) carpeta '{name}' creada"


PREGUNTAS = [
    "¿Qué hora es?",
    "Crea una carpeta llamada pruebas",
    "¿Cuál es la capital de Francia?",
]


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    client = OllamaClient()
    tools = demo.to_ollama_tools()

    for pregunta in PREGUNTAS:
        reply = client.chat([{"role": "user", "content": pregunta}], tools=tools)
        calls = reply.get("tool_calls") or []
        print(f"\nUsuario: {pregunta}")
        if not calls:
            print("  (sin herramienta) JARVIS:", reply.get("content"))
        for call in calls:
            function = call["function"]
            print(f"  Herramienta pedida: {function['name']} {function['arguments']}")
            try:
                print("  Resultado:", demo.get(function["name"]).run(function["arguments"]))
            except ToolError as exc:
                print("  Rechazada por el registro:", exc)

    client.close()


if __name__ == "__main__":
    main()