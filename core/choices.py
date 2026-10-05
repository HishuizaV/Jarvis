"""Opciones entre las que el usuario elige en su siguiente mensaje (resuelto en código, sin el modelo)."""
from __future__ import annotations

import re

from core.paths import KNOWN_FOLDERS
from core.text_utils import normalize_text

ORDINALS = {
    "primero": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercero": 3, "tercera": 3,
    "cuarto": 4, "cuarta": 4, "quinto": 5, "quinta": 5,
}
STOPWORDS = frozenset({
    "los", "las", "una", "uno", "del", "con", "que", "por", "para", "desde", "este", "esta",
    "ese", "esa", "favor", "quiero", "abre", "abrir", "ruta", "carpeta", "archivo", "archivos",
    "donde",
})


class Choices(str):
    """Respuesta de una herramienta que pide elegir entre varias opciones.

    Se comporta como el texto que ve el usuario. Además guarda qué herramienta se ejecuta
    con la opción elegida y con qué argumento; el Agent la recuerda para el siguiente mensaje.
    """

    tool: str
    argument: str
    options: tuple[str, ...]

    def __new__(
        cls, text: str, *, tool: str, argument: str, options: tuple[str, ...]
    ) -> Choices:
        instance = super().__new__(cls, text)
        instance.tool = tool
        instance.argument = argument
        instance.options = options
        return instance


def pick_option(text: str, options: tuple[str, ...]) -> str | None:
    """Elige una opción por número ('2'), por orden ('el segundo') o por una palabra de su ruta.

    Devuelve None si el mensaje no elige claramente una sola opción.
    """
    words = re.findall(r"[a-z0-9_]+", normalize_text(text))
    if not words or not options:
        return None

    for word in words:
        number = ORDINALS.get(word) or (int(word) if word.isdigit() else None)
        if number is not None and 1 <= number <= len(options):
            return options[number - 1]

    tokens = {w for w in words if len(w) >= 3 and w not in STOPWORDS and not w.isdigit()}
    expanded = set(tokens)
    for token in tokens:
        english = KNOWN_FOLDERS.get(token)  # 'descargas' también significa 'downloads'
        if english:
            expanded.add(english.lower())

    searchable = [normalize_text(option) for option in options]
    scores = [sum(1 for token in expanded if token in option) for option in searchable]
    best = max(scores)
    if best == 0:
        return None
    winners = [index for index, score in enumerate(scores) if score == best]
    return options[winners[0]] if len(winners) == 1 else None