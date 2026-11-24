"""Ausgabe-Filter: ``kunde`` und ``projekt`` verlassen den Server nie."""

from typing import Any

VERBOTENE_FELDER = frozenset({"kunde", "projekt"})


def redact(value: Any) -> Any:
    """Entfernt ``kunde`` und ``projekt`` rekursiv aus Dicts und Listen.

    Args:
        value: Beliebige JSON-artige Struktur.

    Returns:
        Kopie ohne die verbotenen Schlüssel.
    """
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k not in VERBOTENE_FELDER}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value
