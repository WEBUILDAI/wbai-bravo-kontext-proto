"""Keyword-Score und optionales Ranking per Claude."""

import json
import logging
import re
from collections.abc import Iterable
from typing import Any, Protocol

from bravo_kontext.eintraege import Eintrag

logger = logging.getLogger(__name__)

_STOPWORTE = frozenset(
    [
        "und",
        "oder",
        "der",
        "die",
        "das",
        "ein",
        "eine",
        "einer",
        "eines",
        "einem",
        "einen",
        "mit",
        "für",
        "fuer",
        "von",
        "vom",
        "zum",
        "zur",
        "im",
        "in",
        "auf",
        "aus",
        "bei",
        "ist",
        "sind",
        "wird",
        "werden",
        "nicht",
        "als",
        "auch",
        "wie",
        "was",
        "wenn",
        "dann",
        "den",
        "dem",
        "des",
        "sich",
        "soll",
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "into",
    ]
)
_WORT = re.compile(r"[\wäöüß][\wäöüß.+-]*", re.UNICODE)

GEWICHT_TITEL = 3
GEWICHT_BESCHREIBUNG = 2
GEWICHT_TECH_TAG = 3
GEWICHT_INHALT = 1
BONUS_TECH = 5


def tokens(text: str) -> set[str]:
    """Zerlegt Text in normalisierte Suchbegriffe.

    Args:
        text: Freitext.

    Returns:
        Menge kleingeschriebener Begriffe ohne Stoppwörter und Ein-/Zwei-Zeichen-Wörter.
    """
    ergebnis: set[str] = set()
    for wort in _WORT.findall(text or ""):
        w = wort.strip(".-+").lower()
        # Zusammengesetzte Begriffe zusätzlich in ihre Teile zerlegen.
        for teil in (w, *w.split("-")):
            if len(teil) >= 3 and teil not in _STOPWORTE:
                ergebnis.add(teil)
    return ergebnis


def keyword_score(eintrag: Eintrag, begriffe: set[str], tech: Iterable[str] = ()) -> int:
    """Bewertet einen Eintrag gegen Suchbegriffe.

    Args:
        eintrag: Der Eintrag.
        begriffe: Suchbegriffe (siehe :func:`tokens`).
        tech: Bevorzugte Technologien (Bonus bei Überschneidung).

    Returns:
        Ganzzahliger Score, 0 heißt kein Treffer.
    """
    titel = tokens(eintrag.titel)
    beschreibung = tokens(eintrag.beschreibung)
    meta = {t.lower() for t in (*eintrag.tech, *eintrag.tags)}
    meta |= {teil for t in eintrag.tags for teil in t.split("-") if len(teil) >= 3}
    inhalt = tokens(eintrag.inhalt)
    score = 0
    for b in begriffe:
        score += GEWICHT_TITEL * (b in titel)
        score += GEWICHT_BESCHREIBUNG * (b in beschreibung)
        score += GEWICHT_TECH_TAG * (b in meta)
        score += GEWICHT_INHALT * (b in inhalt)
    tech_set = {t.lower() for t in tech}
    if tech_set & {t.lower() for t in eintrag.tech}:
        score += BONUS_TECH
    return score


def nach_keyword(
    eintraege: Iterable[Eintrag], text: str, tech: Iterable[str] = ()
) -> list[tuple[Eintrag, int]]:
    """Sortiert Einträge nach Keyword-Score (absteigend, nur Treffer > 0).

    Args:
        eintraege: Kandidaten.
        text: Suchtext.
        tech: Bevorzugte Technologien.

    Returns:
        Liste aus (Eintrag, Score), stabil nach Score und ID sortiert.
    """
    begriffe = tokens(text)
    tech = list(tech)
    bewertet = [(e, keyword_score(e, begriffe, tech)) for e in eintraege]
    treffer = [(e, s) for e, s in bewertet if s > 0]
    return sorted(treffer, key=lambda es: (-es[1], es[0].id))


class Ranker(Protocol):
    """Ordnet Kandidaten für eine Aufgabe."""

    async def rank(self, aufgabe: str, kandidaten: list[Eintrag], limit: int) -> list[str]:
        """Gibt IDs in Relevanzreihenfolge zurück."""
        ...


_SYSTEM = (
    "Du bewertest interne Wissenseinträge für eine Programmieraufgabe. "
    'Antworte ausschließlich mit JSON der Form {"ids": ["<id>", ...]}: die relevanten IDs, '
    "relevanteste zuerst, höchstens LIMIT Stück. Lass irrelevante Einträge weg. "
    "Erfinde keine IDs."
)


class ClaudeRanker:
    """Ranking per Claude über das offizielle Anthropic SDK.

    Args:
        api_key: Anthropic API-Key.
        model: Modell-ID.
        client: Optionaler vorkonfigurierter ``AsyncAnthropic``-Client (für Tests).
    """

    def __init__(self, api_key: str, model: str, client: Any = None) -> None:
        if client is None:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key, max_retries=1, timeout=15.0)
        self._client = client
        self._model = model

    async def rank(self, aufgabe: str, kandidaten: list[Eintrag], limit: int) -> list[str]:
        """Lässt Claude die Kandidaten ordnen.

        Args:
            aufgabe: Aufgabenbeschreibung.
            kandidaten: Vorgefilterte Kandidaten.
            limit: Maximale Anzahl.

        Returns:
            Bekannte IDs in Relevanzreihenfolge.

        Raises:
            ValueError: Wenn die Antwort kein verwertbares JSON enthält.
        """
        liste = [
            {
                "id": e.id,
                "typ": e.typ,
                "titel": e.titel,
                "beschreibung": e.beschreibung,
                "tech": list(e.tech),
                "tags": list(e.tags),
            }
            for e in kandidaten
        ]
        nachricht = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM.replace("LIMIT", str(limit)),
            messages=[
                {
                    "role": "user",
                    "content": f"Aufgabe:\n{aufgabe}\n\nEinträge:\n"
                    + json.dumps(liste, ensure_ascii=False),
                }
            ],
        )
        text = "".join(
            getattr(block, "text", "") for block in nachricht.content if block.type == "text"
        )
        start, ende = text.find("{"), text.rfind("}")
        if start < 0 or ende < start:
            raise ValueError("Keine JSON-Antwort")
        ids = json.loads(text[start : ende + 1]).get("ids", [])
        bekannt = {e.id for e in kandidaten}
        ergebnis: list[str] = []
        for i in ids:
            if isinstance(i, str) and i in bekannt and i not in ergebnis:
                ergebnis.append(i)
        return ergebnis[:limit]
