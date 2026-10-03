"""JARVIS: punto de entrada. Por ahora, un chat en la terminal."""
from __future__ import annotations

from config.logging_config import setup_logging
from core.agent import Agent
from core.intent_router import IntentRouter
from core.ollama_client import OllamaClient
from tools import load_tools


def main() -> None:
    setup_logging()
    load_tools()

    client = OllamaClient()
    try:
        if not client.is_available():
            print("Ollama no está corriendo. Ábrelo (ícono en la bandeja) y vuelve a intentar.")
            return

        agent = Agent(IntentRouter(client))
        print("JARVIS listo. Escribe 'salir' para terminar.")
        while True:
            try:
                text = input("\nTú: ")
            except (EOFError, KeyboardInterrupt):
                break
            if text.strip().lower() == "salir":
                break
            print("JARVIS:", agent.handle(text))
    finally:
        client.close()


if __name__ == "__main__":
    main()