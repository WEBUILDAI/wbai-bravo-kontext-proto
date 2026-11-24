import json

import httpx
import pytest
from starlette.testclient import TestClient

from bravo_kontext.app import create_app
from bravo_kontext.github_app import GitHubApp
from bravo_kontext.vorschlaege import OfflineIssueBackend, VorschlagDienst
from tests.conftest import assert_kein_kunde_projekt, call_tool

pytestmark = pytest.mark.anyio
REPO = "WEBUILDAI/wbai-bravo-sample-proto"


@pytest.fixture
def backend(settings):
    return OfflineIssueBackend(settings.bot_login)


@pytest.fixture
def vd(settings, backend):
    return VorschlagDienst(settings, backend, offline=True)


async def _anlegen(vd, autor="lse"):
    return await vd.vorschlag_anlegen(
        "Filter nach Preis ergänzen", "GET /items soll auch nach max_preis filtern.", autor
    )


async def test_vorschlag_anlegen(vd, backend):
    ergebnis = await _anlegen(vd)
    assert ergebnis["status"] == "angelegt" and ergebnis["modus"] == "offline"
    issue = backend.issues[ergebnis["issue"]]
    assert [label["name"] for label in issue["labels"]] == ["triage"]
    assert issue["body"].startswith("[PROTOTYP]")
    assert "<!-- bravo-autor: lse -->" in issue["body"]
    assert issue["title"] == "Vorschlag: Filter nach Preis ergänzen"


@pytest.mark.parametrize(
    "titel,beschreibung,autor",
    [
        ("Ok Titel", "Beschreibung lang genug", "jemand@example.org"),
        ("Ok Titel", "Beschreibung lang genug", "X"),
        ("kurz", "Beschreibung lang genug", "lse"),
        ("Ok Titel", "zu kurz", "lse"),
    ],
)
async def test_vorschlag_validierung(vd, backend, titel, beschreibung, autor):
    ergebnis = await vd.vorschlag_anlegen(titel, beschreibung, autor)
    assert ergebnis["status"] == "abgelehnt"
    assert not backend.issues


async def test_rueckfragen_und_antworten(vd, backend, settings):
    nummer = (await _anlegen(vd))["issue"]
    fremd = (await _anlegen(vd, autor="abc"))["issue"]
    assert (await vd.meine_rueckfragen("lse"))["rueckfragen"] == []

    await backend.create_comment(REPO, nummer, "Welche Währung?", login="claude[bot]")
    await backend.create_comment(REPO, fremd, "Frage an abc", login="claude[bot]")
    rueck = (await vd.meine_rueckfragen("LSE"))["rueckfragen"]
    assert [r["issue"] for r in rueck] == [nummer]
    assert rueck[0]["frage"] == "Welche Währung?" and rueck[0]["von"] == "claude[bot]"

    st = await vd.status(nummer)
    assert st["phase"] == "in Prüfung" and st["rueckfrage_offen"] is True

    assert (await vd.antworten(nummer, "EUR", "abc"))["status"] == "abgelehnt"
    antwort = await vd.antworten(nummer, "EUR", "lse")
    assert antwort["status"] == "beantwortet"
    assert backend.comments[nummer][-1]["body"].startswith("**Antwort von lse**")
    assert backend.comments[nummer][-1]["user"]["login"] == settings.bot_login
    assert (await vd.meine_rueckfragen("lse"))["rueckfragen"] == []
    assert (await vd.status(nummer))["rueckfrage_offen"] is False


async def test_antworten_und_status_grenzen(vd, backend):
    assert (await vd.antworten(99, "x", "lse"))["status"] == "abgelehnt"
    assert "fehler" in await vd.status(99)
    nummer = (await _anlegen(vd))["issue"]
    assert (await vd.antworten(nummer, "", "lse"))["status"] == "abgelehnt"
    backend.issues[nummer]["state"] = "closed"
    assert (await vd.antworten(nummer, "x", "lse"))["status"] == "abgelehnt"
    assert (await vd.status(nummer))["phase"] == "erledigt"
    backend.issues[nummer]["state_reason"] = "not_planned"
    assert (await vd.status(nummer))["phase"] == "abgelehnt"
    backend.issues[nummer] |= {"state": "open", "labels": [{"name": "ready"}]}
    assert (await vd.status(nummer))["phase"] == "bereit zur Umsetzung"


async def test_fremdes_issue_ohne_marker(vd, backend):
    issue = await backend.create_issue(REPO, "Fremd", "kein Marker", ["triage"])
    assert "fehler" in await vd.status(issue["number"])
    assert (await vd.antworten(issue["number"], "x", "lse"))["status"] == "abgelehnt"


async def test_github_backend(settings):
    aufrufe = []

    def handler(request: httpx.Request) -> httpx.Response:
        aufrufe.append((request.method, request.url.path, request.url.params.get("labels")))
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "t"})
        if request.method == "POST" and request.url.path.endswith("/issues"):
            body = json.loads(request.content)
            assert body["labels"] == ["triage"]
            return httpx.Response(201, json={"number": 5, "html_url": "https://gh/5"})
        if request.method == "GET" and request.url.path.endswith("/issues"):
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 5,
                        "title": "Vorschlag: X",
                        "html_url": "https://gh/5",
                        "body": "<!-- bravo-autor: lse -->",
                        "labels": [{"name": "triage"}],
                        "state": "open",
                    },
                    {"number": 6, "pull_request": {}, "labels": [], "body": ""},
                ],
            )
        if request.url.path.endswith("/issues/5/comments"):
            return httpx.Response(200, json=[{"body": "Frage?", "user": {"login": "maintainer"}}])
        return httpx.Response(404, json={"message": "Not Found"})

    gh = GitHubApp.__new__(GitHubApp)
    GitHubApp.__init__(gh, "1", "unbenutzt", "2", transport=httpx.MockTransport(handler))
    gh._token, gh._token_ablauf = "t", 1e12  # JWT-Erzeugung überspringen
    vd = VorschlagDienst.aus_settings(settings, gh)
    assert not vd.offline
    angelegt = await _anlegen(vd)
    assert angelegt == {"status": "angelegt", "issue": 5, "url": "https://gh/5"}
    rueck = await vd.meine_rueckfragen("lse")
    assert [r["issue"] for r in rueck["rueckfragen"]] == [5]
    assert ("GET", f"/repos/{REPO}/issues", "triage") in aufrufe


def test_vorschlag_tools_ueber_http(settings, dienst):
    backend = OfflineIssueBackend(settings.bot_login)
    vd = VorschlagDienst(settings, backend, offline=True)
    with TestClient(create_app(settings, dienst, vorschlaege=vd)) as c:
        angelegt = call_tool(
            c,
            "vorschlag_anlegen",
            {
                "titel": "Neuer Endpunkt",
                "beschreibung": "Bitte GET /health ergänzen.",
                "autor": "lse",
            },
        )["structuredContent"]
        nummer = angelegt["issue"]
        backend.comments[nummer].append(
            {"body": "Mit Version?", "user": {"login": "claude[bot]"}, "created_at": "x"}
        )
        rueck = call_tool(c, "meine_rueckfragen", {"autor": "lse"})["structuredContent"]
        assert rueck["rueckfragen"][0]["issue"] == nummer
        antwort = call_tool(c, "antworten", {"issue": nummer, "text": "Ja", "autor": "lse"})
        assert antwort["structuredContent"]["status"] == "beantwortet"
        status = call_tool(c, "status", {"issue": nummer})["structuredContent"]
        assert status["rueckfrage_offen"] is False
        for ergebnis in (angelegt, rueck, antwort, status):
            assert_kein_kunde_projekt(ergebnis)
