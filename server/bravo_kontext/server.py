"""MCP-Server-Definition (FastMCP, Streamable HTTP)."""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from bravo_kontext.config import Settings
from bravo_kontext.filter import redact
from bravo_kontext.vorschlaege import VorschlagDienst
from bravo_kontext.wissen import WissensDienst

INSTRUCTIONS = (
    "Wissens-MCP für Bravo (PROTOTYP). Liefert kuratiertes Wissen aus wbai-bravo-wissen-proto. "
    "Zu Beginn einer Aufgabe context_pack aufrufen; Details mit get, Nachbarn mit related. "
    "Neue Learnings am Ende einer Aufgabe mit propose als PR vorschlagen. "
    "Änderungswünsche an der Anwendung mit vorschlag_anlegen einreichen; Rückfragen dazu mit "
    "meine_rueckfragen abholen und mit antworten beantworten; Stand mit status."
)


def transport_security(settings: Settings) -> TransportSecuritySettings:
    """Baut die DNS-Rebinding-Einstellungen aus ``BRAVO_ALLOWED_HOSTS``.

    Args:
        settings: Konfiguration.

    Returns:
        TransportSecuritySettings; ``*`` schaltet die Prüfung ab.
    """
    if "*" in settings.allowed_hosts:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=[f"https://{h}" for h in settings.allowed_hosts]
        + [f"http://{h}" for h in settings.allowed_hosts],
    )


def build_mcp(
    settings: Settings, dienst: WissensDienst, vorschlaege: VorschlagDienst | None = None
) -> FastMCP:
    """Erzeugt den FastMCP-Server mit allen Wissens- und Vorschlags-Tools.

    Args:
        settings: Konfiguration.
        dienst: Fachlogik für Wissen.
        vorschlaege: Fachlogik für Änderungsvorschläge; Standard aus ``settings``.

    Returns:
        Konfigurierter FastMCP-Server (stateless, JSON-Antworten).
    """
    mcp = FastMCP(
        "bravo-kontext",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        transport_security=transport_security(settings),
    )

    @mcp.tool()
    async def context_pack(
        aufgabe: str, tech: list[str] | None = None, max: int = 10  # noqa: A002
    ) -> dict[str, Any]:
        """Passender Kontext für eine Aufgabe, nach Relevanz geordnet.

        Args:
            aufgabe: Was soll umgesetzt werden (Freitext).
            tech: Bevorzugte Technologien, z. B. ["python", "fastapi"].
            max: Maximale Anzahl Einträge (Standard 10, höchstens 25).
        """
        return await dienst.context_pack(aufgabe, tech, max)

    @mcp.tool()
    async def search(query: str, typ: str | None = None, tech: str | None = None) -> dict[str, Any]:
        """Keyword-Suche über alle gültigen Wissenseinträge.

        Args:
            query: Suchbegriffe.
            typ: Optional: entscheidung, learning, muster, gotcha oder standard.
            tech: Optional: genau eine Technologie als Filter.
        """
        return await dienst.search(query, typ, tech)

    @mcp.tool()
    async def get(id: str) -> dict[str, Any]:  # noqa: A002
        """Einen Wissenseintrag vollständig abrufen.

        Args:
            id: ID im Format <typ>/<slug>.
        """
        return await dienst.get(id)

    @mcp.tool()
    async def related(id: str, max: int = 5) -> dict[str, Any]:  # noqa: A002
        """Verwandte Einträge zu einem Eintrag.

        Args:
            id: ID im Format <typ>/<slug>.
            max: Maximale Anzahl (Standard 5).
        """
        return await dienst.related(id, max)

    @mcp.tool()
    async def propose(
        typ: str,
        titel: str,
        beschreibung: str,
        tech: list[str],
        inhalt: str,
        tags: list[str] | None = None,
        quelle: str | None = None,
        gueltig_bis: str | None = None,
    ) -> dict[str, Any]:
        """Neuen Wissenseintrag als Pull Request im Wissens-Repo vorschlagen.

        Keine Kundennamen, Secrets oder personenbezogenen Daten in Titel oder Inhalt.

        Args:
            typ: entscheidung, learning, muster, gotcha oder standard.
            titel: Kurzer Titel (5-120 Zeichen).
            beschreibung: Ein Satz, wann der Eintrag relevant ist (10-300 Zeichen).
            tech: Technologien in Kleinbuchstaben, z. B. ["python"].
            inhalt: Markdown-Inhalt des Eintrags.
            tags: Optionale Schlagworte in Kleinbuchstaben.
            quelle: Optionale HTTPS-URL der Quelle (z. B. PR-Link).
            gueltig_bis: Optionales Ablaufdatum (YYYY-MM-DD), Standard in einem Jahr.
        """
        return await dienst.propose(
            typ, titel, beschreibung, tech, inhalt, tags, quelle, gueltig_bis
        )

    vorschlaege = vorschlaege or VorschlagDienst.aus_settings(settings, dienst.github)

    @mcp.tool()
    async def vorschlag_anlegen(
        titel: str, beschreibung: str, autor: str, kontext: str | None = None
    ) -> dict[str, Any]:
        """Änderungsvorschlag für die Anwendung einreichen (Issue mit Label triage).

        Keine Kundennamen, Secrets oder personenbezogenen Daten angeben.

        Args:
            titel: Kurzer Titel (5-120 Zeichen).
            beschreibung: Was soll sich ändern und warum.
            autor: Dein Kürzel oder GitHub-Handle (keine E-Mail-Adresse).
            kontext: Optional: betroffene Stelle, Link oder Beispiel.
        """
        return redact(await vorschlaege.vorschlag_anlegen(titel, beschreibung, autor, kontext))

    @mcp.tool()
    async def meine_rueckfragen(autor: str) -> dict[str, Any]:
        """Offene Rückfragen zu deinen Vorschlägen abholen.

        Args:
            autor: Dein Kürzel oder GitHub-Handle wie bei vorschlag_anlegen.
        """
        return redact(await vorschlaege.meine_rueckfragen(autor))

    @mcp.tool()
    async def antworten(issue: int, text: str, autor: str) -> dict[str, Any]:
        """Eine Rückfrage zu deinem Vorschlag beantworten.

        Args:
            issue: Nummer des Vorschlags.
            text: Deine Antwort.
            autor: Dein Kürzel oder GitHub-Handle wie bei vorschlag_anlegen.
        """
        return redact(await vorschlaege.antworten(issue, text, autor))

    @mcp.tool()
    async def status(issue: int) -> dict[str, Any]:
        """Stand eines Vorschlags: Phase, Labels, offene Rückfrage, letzte Kommentare.

        Args:
            issue: Nummer des Vorschlags.
        """
        return redact(await vorschlaege.status(issue))

    return mcp
