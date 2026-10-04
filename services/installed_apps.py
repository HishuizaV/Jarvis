"""Descubre las aplicaciones instaladas en Windows (Menú Inicio) y las busca por nombre."""
from __future__ import annotations

import difflib
import json
import logging
import re
import subprocess
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from config.settings import BASE_DIR

logger = logging.getLogger(__name__)

CACHE_FILE = BASE_DIR / "data" / "installed_apps.json"
CACHE_MAX_AGE = 24 * 3600      # la caché se renueva cada 24 horas
REFRESH_MIN_INTERVAL = 300     # si no se encuentra una app, se reconsulta como máximo cada 5 min
MAX_OPTIONS = 5
MIN_QUERY_LENGTH = 3
NOISE_WORDS = frozenset({"uninstall", "desinstalar", "desinstalador", "readme"})

# Comando fijo: nunca incluye texto del usuario ni del modelo.
POWERSHELL_COMMAND = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "Get-StartApps | ConvertTo-Json -Compress"
)


@dataclass(frozen=True)
class InstalledApp:
    """Una aplicación del Menú Inicio: nombre visible e identificador de Windows."""

    name: str
    app_id: str

    @property
    def launch_target(self) -> str:
        """Destino para os.startfile: abre la app a través de la carpeta de aplicaciones."""
        return f"shell:AppsFolder\\{self.app_id}"


@dataclass(frozen=True)
class SearchResult:
    """Resultado de buscar una app: 'match', 'ambiguous', 'suggestion', 'none' o 'unavailable'."""

    kind: str
    apps: tuple[InstalledApp, ...] = ()


def normalize_name(text: str) -> str:
    """'Adobe Photoshop 2025' -> 'adobe photoshop 2025' (sin tildes, símbolos ni mayúsculas)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    no_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", no_accents).split())


def parse_start_apps(raw: str) -> list[InstalledApp]:
    """Convierte la salida JSON de Get-StartApps en una lista de apps (sin duplicados ni ruido)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Get-StartApps no devolvió un JSON válido.")
        return []
    if isinstance(data, dict):  # con un solo resultado, PowerShell devuelve un objeto
        data = [data]

    apps: list[InstalledApp] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name", "")).strip()
        app_id = str(item.get("AppID", "")).strip()
        key = normalize_name(name)
        if not key or not app_id or key in seen or NOISE_WORDS & set(key.split()):
            continue
        seen.add(key)
        apps.append(InstalledApp(name, app_id))
    return apps


def query_start_apps(timeout: float = 30.0) -> list[InstalledApp]:
    """Consulta a Windows las apps del Menú Inicio. Si falla, devuelve una lista vacía."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_COMMAND],
            capture_output=True,
            text=True,
            encoding="utf-8-sig",
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("No se pudo ejecutar Get-StartApps: %s", exc)
        return []
    if result.returncode != 0:
        logger.warning("Get-StartApps terminó con error %s: %s", result.returncode, result.stderr.strip())
        return []
    return parse_start_apps(result.stdout)


def find_matches(query: str, apps: list[InstalledApp]) -> SearchResult:
    """Busca por nombre: exacto, contenido, o parecido (para erratas)."""
    wanted = normalize_name(query)
    if len(wanted) < MIN_QUERY_LENGTH:
        return SearchResult("none")

    by_name = {normalize_name(app.name): app for app in apps}
    if wanted in by_name:
        return SearchResult("match", (by_name[wanted],))

    wanted_words = set(wanted.split())
    contained = [app for name, app in by_name.items() if wanted_words <= set(name.split())]
    if len(contained) == 1:
        return SearchResult("match", tuple(contained))
    if len(contained) > 1:
        options = sorted(contained, key=lambda app: app.name)[:MAX_OPTIONS]
        return SearchResult("ambiguous", tuple(options))

    close = difflib.get_close_matches(wanted, list(by_name), n=MAX_OPTIONS, cutoff=0.75)
    if close:
        return SearchResult("suggestion", tuple(by_name[name] for name in close))
    return SearchResult("none")


class InstalledApps:
    """Índice de apps instaladas, con caché en disco."""

    def __init__(
        self,
        cache_file: Path = CACHE_FILE,
        loader: Callable[[], list[InstalledApp]] | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._cache_file = cache_file
        self._loader = loader or query_start_apps
        self._now = now
        self._apps: list[InstalledApp] | None = None
        self._loaded_at = 0.0

    def all_apps(self) -> list[InstalledApp]:
        """Todas las apps conocidas."""
        return list(self._get_apps())

    def search(self, query: str) -> SearchResult:
        """Busca una app por nombre. Si no la encuentra, reconsulta a Windows (con límite de frecuencia)."""
        apps = self._get_apps()
        if not apps and self._can_refresh():
            apps = self._refresh()
        if not apps:
            return SearchResult("unavailable")

        result = find_matches(query, apps)
        if result.kind == "none" and self._can_refresh():  # quizá se instaló hace poco
            apps = self._refresh()
            result = find_matches(query, apps)
        return result

    def _can_refresh(self) -> bool:
        return self._now() - self._loaded_at > REFRESH_MIN_INTERVAL

    def _get_apps(self) -> list[InstalledApp]:
        if self._apps is None:
            cached = self._read_cache()
            if cached is None:
                return self._refresh()
            self._apps, self._loaded_at = cached
        return self._apps

    def _refresh(self) -> list[InstalledApp]:
        apps = self._loader()
        self._loaded_at = self._now()
        if apps:
            self._apps = apps
            self._write_cache(apps)
        elif self._apps is None:
            self._apps = []
        return self._apps or []

    def _read_cache(self) -> tuple[list[InstalledApp], float] | None:
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            saved_at = float(data["saved_at"])
            apps = [InstalledApp(item["name"], item["app_id"]) for item in data["apps"]]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not apps or self._now() - saved_at > CACHE_MAX_AGE:
            return None
        return apps, saved_at

    def _write_cache(self, apps: list[InstalledApp]) -> None:
        data = {
            "saved_at": self._loaded_at,
            "apps": [{"name": app.name, "app_id": app.app_id} for app in apps],
        }
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            logger.warning("No se pudo guardar la caché de aplicaciones: %s", exc)