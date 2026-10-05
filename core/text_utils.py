"""Utilidades de texto compartidas."""
from __future__ import annotations

import unicodedata


def normalize_text(text: str) -> str:
    """Minúsculas y sin tildes: 'Batería' -> 'bateria'."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")