"""Änderungsvorschläge aus der Claude-App als Issues im sample-Repo (S9)."""

import itertools
import logging
import re
from datetime import UTC, datetime
from typing import Any, Protocol

from bravo_kontext.config import Settings
from bravo_kontext.github_app import GitHubApp, GitHubFehler
from bravo_kontext.logging_setup import log_auslieferung

logger = logging.getLogger(__name__)

LABEL_TRIAGE = "triage"
LABEL_READY = "ready"
AUTOR_MUSTER = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")
_MARKER = "<!-- bravo-autor: {autor} -->"
_MARKER_RE = re.compile(r"<!-- bravo-autor: ([a-z0-9-]+) -->")
MAX_TEXT = 4000
AUSZUG = 500


class IssueBackend(Protocol):
    """Minimale Issue-API (GitHub oder In-Memory)."""

    async def create_issue(
        self, repo: str, title: str, body: str, labels: list[str]
    ) -> dict[str, Any]:
        """Legt ein Issue an."""
        ...

    async def list_issues(self, repo: str, labels: list[str], state: str = "open") -> list[dict]:
        """Listet Issues mit Labels."""
        ...

    async def get_issue(self, repo: str, number: int) -> dict[str, Any]:
        """Liest ein Issue."""
        ...

    async def list_comments(self, repo: str, number: int) -> list[dict]:
        """Listet Kommentare."""
        ...

    async def create_comment(self, repo: str, number: int, body: str) -> dict[str, Any]:
        """Kommentiert ein Issue."""
        ...


class OfflineIssueBackend:
    """In-Memory-Ersatz für GitHub-Issues (Offline-Modus und Tests).

    Args:
        bot_login: Login, unter dem Issues und Kommentare dieses Servers erscheinen.
    """

    def __init__(self, bot_login: str) -> None:
        self.bot_login = bot_login
        self.issues: dict[int, dict[str, Any]] = {}
        self.comments: dict[int, list[dict[str, Any]]] = {}
        self._nummern = itertools.count(1)

    @staticmethod
    def _jetzt() -> str:
        return datetime.now(UTC).isoformat()

    async def create_issue(
        self, repo: str, title: str, body: str, labels: list[str]
    ) -> dict[str, Any]:
        """Legt ein Issue im Speicher an."""
        nummer = next(self._nummern)
        issue = {
            "number": nummer,
            "title": title,
            "body": body,
            "state": "open",
            "state_reason": None,
            "labels": [{"name": n} for n in labels],
            "html_url": f"offline://{repo}/issues/{nummer}",
            "user": {"login": self.bot_login, "type": "Bot"},
            "created_at": self._jetzt(),
            "updated_at": self._jetzt(),
        }
        self.issues[nummer] = issue
        self.comments[nummer] = []
        return issue

    async def list_issues(self, repo: str, labels: list[str], state: str = "open") -> list[dict]:
        """Filtert die gespeicherten Issues."""
        ergebnis = []
        for issue in self.issues.values():
            namen = {label["name"] for label in issue["labels"]}
            if set(labels) <= namen and (state == "all" or issue["state"] == state):
                ergebnis.append(issue)
        return ergebnis

    async def get_issue(self, repo: str, number: int) -> dict[str, Any]:
        """Liest ein gespeichertes Issue.

        Raises:
            GitHubFehler: 404, wenn es das Issue nicht gibt.
        """
        if number not in self.issues:
            raise GitHubFehler(404, "Not Found")
        return self.issues[number]

    async def list_comments(self, repo: str, number: int) -> list[dict]:
        """Gibt die Kommentare eines Issues zurück."""
        await self.get_issue(repo, number)
        return list(self.comments[number])

    async def create_comment(
        self, repo: str, number: int, body: str, login: str | None = None
    ) -> dict[str, Any]:
        """Fügt einen Kommentar hinzu (``login`` simuliert fremde Autoren in Tests)."""
        await self.get_issue(repo, number)
        kommentar = {
            "body": body,
            "user": {"login": login or self.bot_login},
            "created_at": self._jetzt(),
        }
        self.comments[number].append(kommentar)
        self.issues[number]["updated_at"] = kommentar["created_at"]
        return kommentar


def _label_namen(issue: dict[str, Any]) -> list[str]:
    return [label["name"] if isinstance(label, dict) else str(label) for label in issue["labels"]]


def _autor_von(issue: dict[str, Any]) -> str | None:
    treffer = _MARKER_RE.search(issue.get("body") or "")
    return treffer.group(1) if treffer else None


def _auszug(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= AUSZUG else text[: AUSZUG - 1] + "…"


def _phase(issue: dict[str, Any]) -> str:
    if issue["state"] == "closed":
        return "abgelehnt" if issue.get("state_reason") == "not_planned" else "erledigt"
    labels = set(_label_namen(issue))
    if LABEL_READY in labels:
        return "bereit zur Umsetzung"
    if LABEL_TRIAGE in labels:
        return "in Prüfung"
    return "offen"


class VorschlagDienst:
    """Implementiert ``vorschlag_anlegen``, ``meine_rueckfragen``, ``antworten`` und ``status``.

    Args:
        settings: Konfiguration (``SAMPLE_REPO``, ``BRAVO_BOT_LOGIN``).
        backend: GitHub-App-Client oder In-Memory-Backend.
        offline: Ob das Backend nur im Speicher arbeitet (wird in Antworten gemeldet).
    """

    def __init__(self, settings: Settings, backend: IssueBackend, offline: bool) -> None:
        self.settings = settings
        self.backend = backend
        self.offline = offline

    @classmethod
    def aus_settings(cls, settings: Settings, github: GitHubApp | None) -> "VorschlagDienst":
        """Wählt das Backend anhand der Konfiguration.

        Args:
            settings: Konfiguration.
            github: GitHub-App-Client oder None für den Offline-Modus.

        Returns:
            Fertiger Dienst.
        """
        if github is None:
            return cls(settings, OfflineIssueBackend(settings.bot_login), offline=True)
        return cls(settings, github, offline=False)

    def _antwort(self, daten: dict[str, Any]) -> dict[str, Any]:
        if self.offline:
            daten["modus"] = "offline"
            daten["hinweis"] = "Keine GitHub App konfiguriert, Daten nur im Speicher."
        return daten

    @staticmethod
    def _pruefe_autor(autor: str) -> str | None:
        if not AUTOR_MUSTER.match(autor or ""):
            return (
                "autor muss ein Kürzel oder GitHub-Handle sein "
                "(klein, a-z, 0-9, Bindestrich, 2-39 Zeichen; keine E-Mail-Adresse)"
            )
        return None

    async def _eigenes_issue(self, issue_nummer: int) -> dict[str, Any] | None:
        try:
            issue = await self.backend.get_issue(self.settings.sample_repo, issue_nummer)
        except GitHubFehler as exc:
            if exc.status == 404:
                return None
            raise
        if "pull_request" in issue or _autor_von(issue) is None:
            return None
        return issue

    async def vorschlag_anlegen(
        self, titel: str, beschreibung: str, autor: str, kontext: str | None = None
    ) -> dict[str, Any]:
        """Legt einen Änderungsvorschlag als Issue mit Label ``triage`` an.

        Args:
            titel: Kurzer Titel (5–120 Zeichen).
            beschreibung: Was soll sich ändern und warum.
            autor: Kürzel oder GitHub-Handle der vorschlagenden Person.
            kontext: Optionaler Zusatz (z. B. betroffene Datei, Link).

        Returns:
            Dict mit ``status``, ``issue`` und ``url`` oder ``fehler``.
        """
        autor = (autor or "").strip().lower()
        if fehler := self._pruefe_autor(autor):
            return {"status": "abgelehnt", "fehler": fehler}
        titel = (titel or "").strip()
        if not 5 <= len(titel) <= 120:
            return {"status": "abgelehnt", "fehler": "titel muss 5-120 Zeichen haben"}
        if not 10 <= len(beschreibung or "") <= MAX_TEXT:
            return {
                "status": "abgelehnt",
                "fehler": f"beschreibung muss 10-{MAX_TEXT} Zeichen haben",
            }
        body = (
            "[PROTOTYP] Änderungsvorschlag aus der Claude-App (Bravo-MCP, `vorschlag_anlegen`).\n\n"
            f"**Vorgeschlagen von:** {autor}\n\n"
            f"## Beschreibung\n{beschreibung.strip()}\n"
        )
        if kontext:
            body += f"\n## Kontext\n{kontext.strip()[:MAX_TEXT]}\n"
        body += "\n" + _MARKER.format(autor=autor) + "\n"
        try:
            issue = await self.backend.create_issue(
                self.settings.sample_repo, f"Vorschlag: {titel}", body, [LABEL_TRIAGE]
            )
        except GitHubFehler as exc:
            logger.warning("vorschlag_anlegen fehlgeschlagen: %s", exc)
            return {"status": "fehler", "fehler": str(exc)}
        log_auslieferung("vorschlag_anlegen", [], issue=issue["number"], autor=autor)
        return self._antwort(
            {"status": "angelegt", "issue": issue["number"], "url": issue["html_url"]}
        )

    async def meine_rueckfragen(self, autor: str) -> dict[str, Any]:
        """Listet offene Vorschläge der Person, deren letzter Kommentar eine Rückfrage ist.

        Eine Rückfrage ist ein Kommentar, der nicht von diesem Server stammt.

        Args:
            autor: Kürzel oder GitHub-Handle wie bei ``vorschlag_anlegen``.

        Returns:
            Dict mit ``rueckfragen`` (Issue, Titel, URL, Frage, von, seit).
        """
        autor = (autor or "").strip().lower()
        if fehler := self._pruefe_autor(autor):
            return {"fehler": fehler}
        repo = self.settings.sample_repo
        issues = await self.backend.list_issues(repo, [LABEL_TRIAGE], state="open")
        rueckfragen = []
        for issue in issues:
            if _autor_von(issue) != autor:
                continue
            kommentare = await self.backend.list_comments(repo, issue["number"])
            if not kommentare:
                continue
            letzter = kommentare[-1]
            if letzter["user"]["login"] == self.settings.bot_login:
                continue
            rueckfragen.append(
                {
                    "issue": issue["number"],
                    "titel": issue["title"],
                    "url": issue["html_url"],
                    "frage": _auszug(letzter["body"]),
                    "von": letzter["user"]["login"],
                    "seit": letzter.get("created_at"),
                }
            )
        log_auslieferung(
            "meine_rueckfragen", [], autor=autor, issues=[r["issue"] for r in rueckfragen]
        )
        return self._antwort({"rueckfragen": rueckfragen})

    async def antworten(self, issue_nummer: int, text: str, autor: str) -> dict[str, Any]:
        """Beantwortet eine Rückfrage zu einem eigenen Vorschlag.

        Args:
            issue_nummer: Nummer des Vorschlags-Issues.
            text: Antworttext.
            autor: Kürzel oder GitHub-Handle; muss zum Vorschlag passen.

        Returns:
            Dict mit ``status`` und ``url`` oder ``fehler``.
        """
        autor = (autor or "").strip().lower()
        if fehler := self._pruefe_autor(autor):
            return {"status": "abgelehnt", "fehler": fehler}
        if not 1 <= len((text or "").strip()) <= MAX_TEXT:
            return {"status": "abgelehnt", "fehler": f"text muss 1-{MAX_TEXT} Zeichen haben"}
        issue = await self._eigenes_issue(issue_nummer)
        if issue is None:
            return {"status": "abgelehnt", "fehler": "Kein Bravo-Vorschlag mit dieser Nummer"}
        if _autor_von(issue) != autor:
            return {"status": "abgelehnt", "fehler": "Vorschlag gehört einer anderen Person"}
        if issue["state"] != "open":
            return {"status": "abgelehnt", "fehler": "Vorschlag ist bereits geschlossen"}
        body = f"**Antwort von {autor}** (über Bravo-MCP):\n\n{text.strip()}"
        try:
            await self.backend.create_comment(self.settings.sample_repo, issue_nummer, body)
        except GitHubFehler as exc:
            logger.warning("antworten fehlgeschlagen: %s", exc)
            return {"status": "fehler", "fehler": str(exc)}
        log_auslieferung("antworten", [], issue=issue_nummer, autor=autor)
        return self._antwort(
            {"status": "beantwortet", "issue": issue_nummer, "url": issue["html_url"]}
        )

    async def status(self, issue_nummer: int) -> dict[str, Any]:
        """Zeigt den Stand eines Vorschlags.

        Args:
            issue_nummer: Nummer des Vorschlags-Issues.

        Returns:
            Dict mit Phase, Labels, offener Rückfrage und den letzten Kommentaren.
        """
        issue = await self._eigenes_issue(issue_nummer)
        if issue is None:
            return {"fehler": "Kein Bravo-Vorschlag mit dieser Nummer"}
        kommentare = await self.backend.list_comments(self.settings.sample_repo, issue_nummer)
        letzte = [
            {"von": k["user"]["login"], "am": k.get("created_at"), "text": _auszug(k["body"])}
            for k in kommentare[-3:]
        ]
        rueckfrage_offen = bool(
            issue["state"] == "open"
            and kommentare
            and kommentare[-1]["user"]["login"] != self.settings.bot_login
        )
        log_auslieferung("status", [], issue=issue_nummer)
        return self._antwort(
            {
                "issue": issue_nummer,
                "titel": issue["title"],
                "url": issue["html_url"],
                "phase": _phase(issue),
                "labels": _label_namen(issue),
                "rueckfrage_offen": rueckfrage_offen,
                "aktualisiert": issue.get("updated_at"),
                "letzte_kommentare": letzte,
            }
        )
