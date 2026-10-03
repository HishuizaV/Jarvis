"""Herramientas de JARVIS. Importar este paquete no registra nada: usa load_tools()."""
import importlib

TOOL_MODULES = ("tools.system",)


def load_tools() -> None:
    """Importa los módulos de herramientas para que se registren en el registro global."""
    for module in TOOL_MODULES:
        importlib.import_module(module)