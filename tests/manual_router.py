"""Prueba manual del Intent Router con el modelo real.

Ejecutar con: python -m tests.manual_router
"""
import logging

from core.intent_router import IntentRouter
from core.ollama_client import OllamaClient
from tests.manual_tool_calling import demo

PREGUNTAS = [
    "Hola, ¿cómo estás?",
    "¿Qué hora es?",
    "Crea una carpeta llamada pruebas",
    "¿Cuál es la capital de Francia?",
    "Explícame qué es una variable en Python",
]


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    client = OllamaClient()
    router = IntentRouter(client, demo)

    for pregunta in PREGUNTAS:
        intent = router.route(pregunta)
        print(f"\nUsuario: {pregunta}")
        if intent.tool_call:
            print(f"  -> HERRAMIENTA: {intent.tool_call.name} {intent.tool_call.arguments}")
        else:
            print(f"  -> TEXTO: {intent.reply}")

    client.close()


if __name__ == "__main__":
    main()