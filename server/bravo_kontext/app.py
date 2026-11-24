"""Host-App: Bearer-Auth, ``/healthz``, ``POST /notify`` und der gemountete MCP-Endpunkt."""

import contextlib
import hmac
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from bravo_kontext import __version__
from bravo_kontext.config import Settings
from bravo_kontext.github_app import GitHubApp
from bravo_kontext.logging_setup import configure_logging, log_auslieferung
from bravo_kontext.quelle import GitHubQuelle, LeereQuelle, LokaleQuelle, WissenQuelle
from bravo_kontext.ranking import ClaudeRanker
from bravo_kontext.server import build_mcp
from bravo_kontext.vorschlaege import VorschlagDienst
from bravo_kontext.wissen import WissensDienst

logger = logging.getLogger(__name__)

OEFFENTLICHE_PFADE = frozenset({"/healthz"})
MAX_NOTIFY_BYTES = 64 * 1024
ADAPTIVE_CARD = "application/vnd.microsoft.card.adaptive"


class BearerAuthMiddleware:
    """Prüft ``Authorization: Bearer <token>`` mit konstantem Zeitvergleich.

    Args:
        app: Nachgelagerte ASGI-App.
        token: Erwartetes Token.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._token = token.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI-Einstieg."""
        if scope["type"] != "http" or scope["path"] in OEFFENTLICHE_PFADE:
            await self.app(scope, receive, send)
            return
        header = dict(scope.get("headers") or []).get(b"authorization", b"")
        schema, _, wert = header.partition(b" ")
        if schema.lower() != b"bearer" or not hmac.compare_digest(wert.strip(), self._token):
            antwort = JSONResponse(
                {"fehler": "nicht autorisiert"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await antwort(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _pruefe_karte(payload: Any) -> str | None:
    """Validiert das Teams-Payload aus ``scripts/notify-teams.sh``.

    Args:
        payload: Geparster JSON-Body.

    Returns:
        Fehlermeldung oder None, wenn gültig.
    """
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return "Erwartet {'type': 'message', 'attachments': [...]}"
    anhaenge = payload.get("attachments")
    if not isinstance(anhaenge, list) or not anhaenge:
        return "attachments fehlt"
    for anhang in anhaenge:
        if not isinstance(anhang, dict) or anhang.get("contentType") != ADAPTIVE_CARD:
            return "Nur Adaptive Cards werden weitergeleitet"
        body = (anhang.get("content") or {}).get("body") or []
        texte = [b.get("text", "") for b in body if isinstance(b, dict) and b.get("text")]
        if not texte or not str(texte[0]).startswith("[PROTOTYP]"):
            return "Karte muss mit [PROTOTYP] beginnen"
    return None


def build_notify(settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
    """Erzeugt den Handler für ``POST /notify``.

    Args:
        settings: Konfiguration (``TEAMS_WEBHOOK_URL``).
        transport: Optionaler httpx-Transport (für Tests).

    Returns:
        Starlette-Endpoint.
    """

    async def notify(request: Request) -> JSONResponse:
        roh = await request.body()
        if len(roh) > MAX_NOTIFY_BYTES:
            return JSONResponse({"fehler": "Payload zu groß"}, status_code=413)
        try:
            payload = json.loads(roh)
        except ValueError:
            return JSONResponse({"fehler": "Kein gültiges JSON"}, status_code=400)
        fehler = _pruefe_karte(payload)
        if fehler:
            return JSONResponse({"fehler": fehler}, status_code=400)
        if not settings.teams_webhook_url:
            log_auslieferung("notify", [], status="noop")
            return JSONResponse({"status": "noop"}, status_code=202)
        try:
            async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
                resp = await client.post(settings.teams_webhook_url, json=payload)
        except httpx.HTTPError:
            logger.warning("Teams-Webhook nicht erreichbar")
            return JSONResponse({"fehler": "Teams nicht erreichbar"}, status_code=502)
        if resp.status_code >= 400:
            log_auslieferung("notify", [], status="fehler", upstream=resp.status_code)
            return JSONResponse({"fehler": "Teams hat abgelehnt"}, status_code=502)
        log_auslieferung("notify", [], status="weitergeleitet", upstream=resp.status_code)
        return JSONResponse({"status": "weitergeleitet"}, status_code=202)

    return notify


async def healthz(_: Request) -> JSONResponse:
    """Liveness-Check ohne Auth."""
    return JSONResponse({"status": "ok", "version": __version__})


def build_dienst(settings: Settings) -> WissensDienst:
    """Verdrahtet Quelle, Ranker und GitHub-Client anhand der Konfiguration.

    Args:
        settings: Konfiguration.

    Returns:
        Fertiger WissensDienst.
    """
    github = (
        GitHubApp(
            settings.github_app_id or "",
            settings.github_app_private_key or "",
            settings.github_app_installation_id or "",
        )
        if settings.github_enabled
        else None
    )
    quelle: WissenQuelle
    if settings.wissen_local_path:
        quelle = LokaleQuelle(settings.wissen_local_path)
        logger.info("Offline-Modus: lese Einträge aus %s", settings.wissen_local_path)
    elif github:
        quelle = GitHubQuelle(
            github, settings.wissen_repo, settings.wissen_ref, settings.cache_ttl_seconds
        )
    else:
        quelle = LeereQuelle()
        logger.warning("Weder WISSEN_LOCAL_PATH noch GitHub App konfiguriert: keine Einträge")
    ranker = (
        ClaudeRanker(settings.anthropic_api_key, settings.ranking_model)
        if settings.anthropic_api_key
        else None
    )
    if ranker is None:
        logger.info("Kein ANTHROPIC_API_KEY: context_pack nutzt reinen Keyword-Score")
    return WissensDienst(settings, quelle, ranker=ranker, github=github)


def create_app(
    settings: Settings,
    dienst: WissensDienst | None = None,
    notify_transport: httpx.AsyncBaseTransport | None = None,
    vorschlaege: VorschlagDienst | None = None,
) -> ASGIApp:
    """Baut die ASGI-App.

    Args:
        settings: Konfiguration.
        dienst: Optional vorgefertigter Dienst (für Tests).
        notify_transport: Optionaler httpx-Transport für ``/notify`` (für Tests).
        vorschlaege: Optional vorgefertigter Vorschlagsdienst (für Tests).

    Returns:
        ASGI-App mit Auth-Middleware.
    """
    dienst = dienst or build_dienst(settings)
    mcp = build_mcp(settings, dienst, vorschlaege)
    mcp_app = mcp.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        # Der Session-Manager muss im Lifespan der Host-App laufen.
        async with mcp.session_manager.run():
            yield

    starlette_app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/notify", build_notify(settings, notify_transport), methods=["POST"]),
            Mount("/", app=mcp_app),
        ],
        lifespan=lifespan,
    )
    return BearerAuthMiddleware(starlette_app, settings.token)


def main() -> None:
    """Startet den Server mit uvicorn (Port aus ``PORT``, Standard 8000)."""
    import os

    settings = Settings.from_env()
    configure_logging(settings.log_format, settings.log_level)
    app = create_app(settings)
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")  # noqa: S104 - Container lauscht auf allen Interfaces
    uvicorn.run(app, host=host, port=port, log_config=None, proxy_headers=True)


if __name__ == "__main__":
    main()
