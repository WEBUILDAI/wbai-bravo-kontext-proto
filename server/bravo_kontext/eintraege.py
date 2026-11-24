"""Wissenseinträge: Parsen, Validieren, öffentliche Sicht."""

import json
import logging
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import yaml

logger = logging.getLogger(__name__)

TYPEN = ("entscheidung", "learning", "muster", "gotcha", "standard")


@lru_cache(maxsize=1)
def schema() -> dict[str, Any]:
    """Lädt das eingefrorene Eintragsschema (Kopie aus dem Wissens-Repo).

    Returns:
        JSON-Schema als Dict.
    """
    text = resources.files("bravo_kontext").joinpath("schema/eintrag.schema.json").read_text()
    return json.loads(text)


@dataclass(frozen=True)
class Eintrag:
    """Ein Wissenseintrag.

    Attributes:
        id: ``<typ>/<slug>``.
        typ: Art des Wissens.
        titel: Titel.
        beschreibung: Ein Satz, wann der Eintrag relevant ist.
        tech: Technologien.
        tags: Schlagworte.
        kunde: Nur Metadatum, wird nie ausgegeben.
        projekt: Nur Metadatum, wird nie ausgegeben.
        quelle: URL der Quelle.
        gueltig_bis: Ablaufdatum.
        inhalt: Markdown-Text nach dem Frontmatter.
    """

    id: str
    typ: str
    titel: str
    beschreibung: str
    tech: tuple[str, ...]
    tags: tuple[str, ...]
    kunde: str
    projekt: str
    quelle: str
    gueltig_bis: date
    inhalt: str

    def ist_abgelaufen(self, heute: date | None = None) -> bool:
        """Prüft, ob ``gueltig_bis`` vor heute liegt.

        Args:
            heute: Vergleichsdatum, Standard ``date.today()``.

        Returns:
            True, wenn der Eintrag abgelaufen ist.
        """
        return self.gueltig_bis < (heute or date.today())

    def oeffentlich(self, mit_inhalt: bool = True) -> dict[str, Any]:
        """Gibt die an Agents auslieferbare Sicht zurück (ohne ``kunde``/``projekt``).

        Args:
            mit_inhalt: Ob der Markdown-Inhalt enthalten sein soll.

        Returns:
            Dict mit Whitelist-Feldern.
        """
        daten: dict[str, Any] = {
            "id": self.id,
            "typ": self.typ,
            "titel": self.titel,
            "beschreibung": self.beschreibung,
            "tech": list(self.tech),
            "tags": list(self.tags),
            "quelle": self.quelle,
            "gueltig_bis": self.gueltig_bis.isoformat(),
        }
        if mit_inhalt:
            daten["inhalt"] = self.inhalt
        return daten


class EintragFehler(ValueError):
    """Ein Eintrag ist ungültig."""


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Trennt YAML-Frontmatter und Markdown-Inhalt.

    Args:
        text: Dateiinhalt.

    Returns:
        Tupel aus Frontmatter-Dict und Inhalt.

    Raises:
        EintragFehler: Wenn kein gültiges Frontmatter vorhanden ist.
    """
    if not text.startswith("---"):
        raise EintragFehler("Frontmatter fehlt")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise EintragFehler("Frontmatter nicht abgeschlossen")
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise EintragFehler("Frontmatter ist kein Mapping")
    return meta, parts[2].strip()


def _normalisiere(meta: dict[str, Any]) -> dict[str, Any]:
    # YAML parst Datumswerte als date; das Schema erwartet Strings.
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in meta.items()}


def parse_eintrag(eintrag_id: str, text: str) -> Eintrag:
    """Parst und validiert einen Eintrag.

    Args:
        eintrag_id: ``<typ>/<slug>`` aus dem Pfad.
        text: Dateiinhalt.

    Returns:
        Der Eintrag.

    Raises:
        EintragFehler: Bei Schemaverletzung oder wenn ``typ`` nicht zum Ordner passt.
    """
    meta, inhalt = split_frontmatter(text)
    meta = _normalisiere(meta)
    try:
        jsonschema.validate(meta, schema())
    except jsonschema.ValidationError as exc:
        raise EintragFehler(f"{eintrag_id}: {exc.message}") from exc
    ordner = eintrag_id.split("/", 1)[0]
    if meta["typ"] != ordner:
        raise EintragFehler(f"{eintrag_id}: typ '{meta['typ']}' passt nicht zum Ordner")
    return Eintrag(
        id=eintrag_id,
        typ=meta["typ"],
        titel=meta["titel"],
        beschreibung=meta["beschreibung"],
        tech=tuple(meta["tech"]),
        tags=tuple(meta["tags"]),
        kunde=meta["kunde"],
        projekt=meta["projekt"],
        quelle=meta["quelle"],
        gueltig_bis=date.fromisoformat(meta["gueltig_bis"]),
        inhalt=inhalt,
    )


def lade_verzeichnis(root: Path) -> list[Eintrag]:
    """Lädt alle gültigen Einträge unter ``<root>/eintraege/<typ>/<slug>.md``.

    Ungültige Dateien werden geloggt und übersprungen.

    Args:
        root: Wurzel eines Klons des Wissens-Repos.

    Returns:
        Liste der Einträge (inklusive abgelaufener; gefiltert wird beim Ausliefern).
    """
    basis = root / "eintraege"
    ergebnis: list[Eintrag] = []
    if not basis.is_dir():
        logger.warning("Kein Verzeichnis eintraege/ unter %s", root)
        return ergebnis
    for pfad in sorted(basis.glob("*/*.md")):
        eintrag_id = f"{pfad.parent.name}/{pfad.stem}"
        try:
            ergebnis.append(parse_eintrag(eintrag_id, pfad.read_text(encoding="utf-8")))
        except (EintragFehler, yaml.YAMLError) as exc:
            logger.warning("Eintrag übersprungen: %s (%s)", eintrag_id, exc)
    return ergebnis


def render_eintrag(meta: dict[str, Any], inhalt: str) -> str:
    """Erzeugt den Dateiinhalt eines Eintrags aus Frontmatter und Inhalt.

    Args:
        meta: Frontmatter (wird gegen das Schema validiert).
        inhalt: Markdown-Inhalt.

    Returns:
        Dateiinhalt mit YAML-Frontmatter.

    Raises:
        EintragFehler: Bei Schemaverletzung.
    """
    try:
        jsonschema.validate(meta, schema())
    except jsonschema.ValidationError as exc:
        raise EintragFehler(exc.message) from exc
    reihenfolge = [
        "typ",
        "titel",
        "beschreibung",
        "tech",
        "tags",
        "kunde",
        "projekt",
        "quelle",
        "gueltig_bis",
    ]
    geordnet = {k: meta[k] for k in reihenfolge}
    front = yaml.safe_dump(geordnet, allow_unicode=True, sort_keys=False, width=1000)
    return f"---\n{front}---\n{inhalt.strip()}\n"
