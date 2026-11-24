"""Quellen für Wissenseinträge: lokaler Klon oder GitHub-Archiv."""

import io
import logging
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Protocol

from bravo_kontext.eintraege import Eintrag, lade_verzeichnis
from bravo_kontext.github_app import GitHubApp

logger = logging.getLogger(__name__)


class WissenQuelle(Protocol):
    """Liefert die aktuelle Liste aller Einträge."""

    async def eintraege(self) -> list[Eintrag]:
        """Gibt alle Einträge zurück (inklusive abgelaufener)."""
        ...


class LokaleQuelle:
    """Liest Einträge aus einem lokalen Klon (``WISSEN_LOCAL_PATH``).

    Args:
        root: Wurzel des Klons.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    async def eintraege(self) -> list[Eintrag]:
        """Lädt die Einträge bei jedem Aufruf neu (Klon kann sich ändern)."""
        return lade_verzeichnis(self.root)


class LeereQuelle:
    """Fallback ohne Konfiguration: keine Einträge."""

    async def eintraege(self) -> list[Eintrag]:
        """Gibt eine leere Liste zurück."""
        return []


class GitHubQuelle:
    """Lädt das Wissens-Repo als Archiv über die GitHub App und cacht es.

    Args:
        github: GitHub-App-Client.
        repo: ``owner/repo``.
        ref: Branch.
        ttl_seconds: Cache-Dauer.
    """

    def __init__(self, github: GitHubApp, repo: str, ref: str, ttl_seconds: int = 300) -> None:
        self._github = github
        self._repo = repo
        self._ref = ref
        self._ttl = ttl_seconds
        self._cache: list[Eintrag] = []
        self._geladen = 0.0

    async def eintraege(self) -> list[Eintrag]:
        """Gibt gecachte Einträge zurück und lädt nach Ablauf der TTL neu."""
        if self._cache and time.monotonic() - self._geladen < self._ttl:
            return self._cache
        try:
            archiv = await self._github.tarball(self._repo, self._ref)
            self._cache = _entpacke_und_lade(archiv)
            self._geladen = time.monotonic()
            logger.info("Wissens-Repo geladen: %d Einträge", len(self._cache))
        except Exception:
            # Bei Fehlern den alten Stand weiter ausliefern.
            logger.exception("Wissens-Repo konnte nicht geladen werden")
        return self._cache


def _entpacke_und_lade(archiv: bytes) -> list[Eintrag]:
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archiv), mode="r:gz") as tar:
            tar.extractall(tmp, filter="data")
        # GitHub packt alles in einen Ordner <owner>-<repo>-<sha>/.
        wurzeln = [p for p in Path(tmp).iterdir() if p.is_dir()]
        if len(wurzeln) != 1:
            return []
        return lade_verzeichnis(wurzeln[0])
