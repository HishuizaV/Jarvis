"""Pruebas del cliente de Ollama con un servidor simulado (no necesitan Ollama)."""
import json

import httpx
import pytest

from core.ollama_client import OllamaClient, OllamaError


def make_client(handler) -> OllamaClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return OllamaClient(model="modelo-prueba", http_client=http)


def test_chat_devuelve_el_mensaje_y_envia_stream_falso():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hola"}})

    reply = make_client(handler).chat([{"role": "user", "content": "hi"}])

    assert reply["content"] == "hola"
    assert seen["payload"]["stream"] is False
    assert seen["payload"]["model"] == "modelo-prueba"


def test_chat_con_error_http_lanza_ollama_error():
    client = make_client(lambda request: httpx.Response(500, text="fallo interno"))
    with pytest.raises(OllamaError):
        client.chat([{"role": "user", "content": "hi"}])


def test_is_available_es_false_si_no_hay_conexion():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin servidor")

    assert make_client(handler).is_available() is False


def test_list_models_devuelve_los_nombres():
    client = make_client(
        lambda request: httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})
    )
    assert client.list_models() == ["llama3.2:3b"]