"""Chat de prueba en la terminal con el agente completo.

Ejecutar con: python -m tests.manual_agent   (escribe 'salir' para terminar)
Las herramientas son simuladas: no tocan tu PC.
"""
from datetime import datetime

from config.logging_config import setup_logging
from core.agent import Agent
from core.intent_router import IntentRouter
from core.ollama_client import OllamaClient
from core.tool_registry import RiskLevel, ToolParameter, ToolRegistry

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
    description="Crea una carpeta en la ruta indicada.",
    risk=RiskLevel.SAFE,
    parameters=[ToolParameter("path", "string", "Ruta de la carpeta")],
)
def create_folder(path: str) -> str:
    return f"(simulado) carpeta '{path}' creada"


@demo.register(
    name="delete_file",
    description="Elimina un archivo.",
    risk=RiskLevel.CONFIRMATION_REQUIRED,
    parameters=[ToolParameter("path", "string", "Ruta del archivo")],
)
def delete_file(path: str) -> str:
    return f"(simulado) archivo '{path}' eliminado"


@demo.register(name="shutdown_pc", description="Apaga el equipo.", risk=RiskLevel.BLOCKED)
def shutdown_pc() -> str:
    return "(simulado) apagando"


def main() -> None:
    setup_logging()
    client = OllamaClient()
    agent = Agent(IntentRouter(client, demo), demo)

    print("JARVIS listo (herramientas simuladas). Escribe 'salir' para terminar.")
    print("Prueba: ¿qué hora es? | crea una carpeta llamada pruebas | "
          "crea una carpeta en C:\\Windows\\prueba | borra el archivo notas.txt")

    while True:
        try:
            text = input("\nTú: ")
        except (EOFError, KeyboardInterrupt):
            break
        if text.strip().lower() == "salir":
            break
        print("JARVIS:", agent.handle(text))

    client.close()


if __name__ == "__main__":
    main()