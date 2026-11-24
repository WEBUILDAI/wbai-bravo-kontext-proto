"""MCP-Server-Definition (FastMCP, Streamable HTTP)."""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from bravo_kontext.config import Settings
from bravo_kontext.wissen import WissensDienst

INSTRUCTIONS = (
    "Wissens-MCP für Bravo (PROTOTYP). Liefert kuratiertes Wissen aus wbai-bravo-wissen-proto. "
    "Zu Beginn einer Aufgabe context_pack aufrufen; Details mit get, Nachbarn mit related. "
    "Neue Learnings am Ende einer Aufgabe mit propose als PR vorschlagen."
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


def build_mcp(settings: Settings, dienst: WissensDienst) -> FastMCP:
    """Erzeugt den FastMCP-Server mit allen Wissens-Tools.

    Args:
        settings: Konfiguration.
        dienst: Fachlogik.

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

    return mcp
