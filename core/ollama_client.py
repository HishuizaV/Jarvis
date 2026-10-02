"""Cliente HTTP para el servidor local de Ollama."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

Message = dict[str, Any]


class OllamaError(Exception):
    """Fallo al comunicarse con Ollama (servidor apagado, error HTTP, respuesta inválida)."""


class OllamaClient:
    """Envía conversaciones al modelo local y devuelve su respuesta."""

    def __init__(
        self,
        base_url: str = settings.ollama_url,
        model: str = settings.model,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._http = http_client or httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(settings.timeout, connect=5.0),
        )

    def close(self) -> None:
        """Cierra la conexión HTTP."""
        self._http.close()

    def is_available(self) -> bool:
        """Indica si el servidor de Ollama responde."""
        try:
            return self._http.get("/").status_code == 200
        except httpx.HTTPError as exc:
            logger.warning("Ollama no responde: %s", exc)
            return False

    def list_models(self) -> list[str]:
        """Devuelve los nombres de los modelos descargados."""
        data = self._request("GET", "/api/tags")
        return [model["name"] for model in data.get("models", [])]

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> Message:
        """Envía la conversación y devuelve el mensaje del asistente.

        El mensaje devuelto trae 'content' y, si el modelo pidió una
        herramienta, también 'tool_calls'.
        """
        options: dict[str, Any] = {"num_ctx": settings.num_ctx}
        if temperature is not None:
            options["temperature"] = temperature

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": settings.keep_alive,
            "options": options,
        }
        if tools:
            payload["tools"] = tools
        if json_mode:
            payload["format"] = "json"

        data = self._request("POST", "/api/chat", json=payload)
        message = data.get("message")
        if not isinstance(message, dict):
            raise OllamaError("La respuesta de Ollama no trae el campo 'message'.")
        return message

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Hace la petición y convierte cualquier fallo en OllamaError."""
        try:
            response = self._http.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = f"Ollama devolvió HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error(detail)
            raise OllamaError(detail) from exc
        except httpx.HTTPError as exc:
            detail = f"No se pudo contactar a Ollama: {exc}"
            logger.error(detail)
            raise OllamaError(detail) from exc
        except ValueError as exc:
            logger.error("Ollama devolvió una respuesta que no es JSON.")
            raise OllamaError("La respuesta de Ollama no es JSON válido.") from exc


if __name__ == "__main__":
    # Prueba manual: python -m core.ollama_client
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    client = OllamaClient()
    if not client.is_available():
        print("Ollama no está corriendo.")
    else:
        print("Modelos:", client.list_models())
        reply = client.chat([{"role": "user", "content": "Dime hola en una frase"}])
        print("JARVIS:", reply["content"])
    client.close()