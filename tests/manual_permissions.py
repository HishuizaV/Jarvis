"""Prueba manual de permisos con el archivo real.

Ejecutar con: python -m tests.manual_permissions
"""
from core.permissions import load_policy
from core.tool_registry import RiskLevel, Tool

CASOS = [
    ("open_app", RiskLevel.SAFE, {"app": "spotify"}),
    ("close_app", RiskLevel.SAFE, {"app": "explorer.exe"}),
    ("close_app", RiskLevel.SAFE, {"app": "python"}),
    ("create_folder", RiskLevel.SAFE, {"path": r"C:\Windows\prueba"}),
    ("create_folder", RiskLevel.SAFE, {"path": r"C:\Users\Public\prueba"}),
    ("run_command", RiskLevel.SAFE, {"command": "Get-Process"}),
    ("run_command", RiskLevel.SAFE, {"command": "Remove-Item C:\\temp\\x.txt"}),
    ("run_command", RiskLevel.SAFE, {"command": "format C:"}),
    ("delete_file", RiskLevel.CONFIRMATION_REQUIRED, {"path": r"C:\Users\Public\x.txt"}),
    ("shutdown_pc", RiskLevel.BLOCKED, {}),
]


def main() -> None:
    policy = load_policy()
    for name, risk, args in CASOS:
        tool = Tool(name=name, description="", risk=risk, func=lambda **kwargs: None)
        result = policy.check(tool, args)
        print(f"{name:14} {str(args):42} -> {result.risk.value:22} permitido={result.allowed}")
        print(f"{'':14} motivo: {result.reason}")


if __name__ == "__main__":
    main()