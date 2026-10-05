"""Prueba manual del monitor con tu hardware real.

Ejecutar con: python -m tests.manual_monitor
"""
from services.process_manager import format_processes, top_processes
from services.system_monitor import format_snapshot, take_snapshot


def main() -> None:
    print(format_snapshot(take_snapshot()))
    print()
    print(format_processes(top_processes("memory"), "memory"))
    print()
    print(format_processes(top_processes("cpu"), "cpu"))


if __name__ == "__main__":
    main()