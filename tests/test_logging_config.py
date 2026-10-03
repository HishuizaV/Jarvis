"""Pruebas del enmascarado de datos sensibles."""
from config.logging_config import redact_arguments, redact_text


def test_redact_text_enmascara_contrasenas():
    assert "hunter2" not in redact_text("mi contraseña es hunter2")
    assert "abc123" not in redact_text("password: abc123")


def test_redact_text_no_toca_texto_normal():
    assert redact_text("abre spotify") == "abre spotify"


def test_redact_arguments_enmascara_por_nombre_y_contenido():
    clean = redact_arguments({"path": "x", "api_key": "abc", "command": "login password=zzz"})
    assert clean["path"] == "x"
    assert clean["api_key"] == "***"
    assert "zzz" not in clean["command"]