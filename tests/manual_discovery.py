"""Prueba manual del descubrimiento de apps instaladas.

Ejecutar con: python -m tests.manual_discovery [nombre ...]
No abre nada: solo busca.
"""
import sys

from services.installed_apps import InstalledApps


def main() -> None:
    index = InstalledApps()
    print(f"{len(index.all_apps())} aplicaciones encontradas en el Menú Inicio.")

    queries = sys.argv[1:] or ["calculadora", "word", "visual studio", "spotify", "zzzzz"]
    for query in queries:
        result = index.search(query)
        names = ", ".join(app.name for app in result.apps) or "-"
        print(f"{query!r:22} -> {result.kind:12} {names}")


if __name__ == "__main__":
    main()