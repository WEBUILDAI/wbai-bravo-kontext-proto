import json
import logging

import httpx
import pytest
from starlette.testclient import TestClient

from bravo_kontext.app import create_app
from bravo_kontext.config import Settings
from bravo_kontext.logging_setup import AUSLIEFERUNG_LOGGER, JsonFormatter
from tests.conftest import TOKEN, assert_kein_kunde_projekt, auth, call_tool, mcp_headers

KARTE = {
    "type": "message",
    "attachments": [
        {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [{"type": "TextBlock", "text": "[PROTOTYP] PR gemergt"}],
            },
        }
    ],
}


def test_healthz_ohne_auth(client):
    assert client.get("/healthz").json()["status"] == "ok"


@pytest.mark.parametrize(
    "header", [None, "Bearer falsch", f"Basic {TOKEN}", f"bearer {TOKEN}x", "Bearer"]
)
def test_auth_abgelehnt(client, header):
    headers = {"Authorization": header} if header else {}
    assert client.post("/mcp", headers=headers, json={}).status_code == 401
    assert client.post("/notify", headers=headers, json=KARTE).status_code == 401


def test_tools_list(client):
    resp = client.post(
        "/mcp", headers=mcp_headers(), json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert resp.status_code == 200
    namen = {t["name"] for t in resp.json()["result"]["tools"]}
    assert {"context_pack", "search", "get", "related", "propose"} <= namen
    assert {"vorschlag_anlegen", "meine_rueckfragen", "antworten", "status"} <= namen


def test_initialize(client):
    resp = client.post(
        "/mcp",
        headers=mcp_headers(),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["serverInfo"]["name"] == "bravo-kontext"


def test_kein_kunde_projekt_in_allen_tools(client):
    aufrufe = [
        ("context_pack", {"aufgabe": "python fastapi mcp pulumi azure", "max": 25}),
        ("search", {"query": ""}),
        ("search", {"query": "fastapi", "tech": "python"}),
        ("get", {"id": "gotcha/fastmcp-lifespan"}),
        ("related", {"id": "learning/items-filter-leere-liste"}),
        (
            "propose",
            {
                "typ": "learning",
                "titel": "Test-Vorschlag über HTTP",
                "beschreibung": "Relevant nur für den Test des Ausgabe-Filters.",
                "tech": ["python"],
                "inhalt": "Inhalt",
            },
        ),
    ]
    for name, args in aufrufe:
        result = call_tool(client, name, args)
        assert_kein_kunde_projekt(result)
        for block in result["content"]:
            assert "fixture-geheim" not in block.get("text", "")
            assert '"kunde"' not in block.get("text", "")


def test_context_pack_ueber_http(client):
    result = call_tool(client, "context_pack", {"aufgabe": "FastMCP lifespan Starlette"})
    ids = [e["id"] for e in result["structuredContent"]["eintraege"]]
    assert ids[0] == "gotcha/fastmcp-lifespan"


def test_fremder_host_abgelehnt(client):
    headers = mcp_headers() | {"Host": "evil.example"}
    resp = client.post(
        "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert resp.status_code == 421


def test_notify_noop_ohne_webhook(client):
    resp = client.post("/notify", headers=auth(), json=KARTE)
    assert resp.status_code == 202 and resp.json()["status"] == "noop"


def test_notify_validierung(client):
    assert client.post("/notify", headers=auth(), content=b"{kaputt").status_code == 400
    ohne_praefix = json.loads(json.dumps(KARTE))
    ohne_praefix["attachments"][0]["content"]["body"][0]["text"] = "Hallo"
    assert client.post("/notify", headers=auth(), json=ohne_praefix).status_code == 400
    assert client.post("/notify", headers=auth(), json={"type": "x"}).status_code == 400
    gross = {"type": "message", "x": "a" * 70000}
    assert client.post("/notify", headers=auth(), json=gross).status_code == 413


@pytest.mark.parametrize("upstream,erwartet", [(200, 202), (500, 502)])
def test_notify_weiterleitung(settings, dienst, upstream, erwartet):
    empfangen = []

    def handler(request: httpx.Request) -> httpx.Response:
        empfangen.append((str(request.url), json.loads(request.content)))
        return httpx.Response(upstream)

    s = Settings(**{**settings.__dict__, "teams_webhook_url": "https://teams.example/hook"})
    app = create_app(s, dienst, notify_transport=httpx.MockTransport(handler))
    with TestClient(app) as c:
        resp = c.post("/notify", headers=auth(), json=KARTE)
    assert resp.status_code == erwartet
    assert empfangen == [("https://teams.example/hook", KARTE)]


def test_json_log_je_auslieferung(client, caplog):
    caplog.set_level(logging.INFO, logger=AUSLIEFERUNG_LOGGER)
    call_tool(client, "context_pack", {"aufgabe": "FastMCP lifespan"})
    records = [r for r in caplog.records if r.name == AUSLIEFERUNG_LOGGER]
    assert len(records) == 1
    zeile = json.loads(JsonFormatter().format(records[0]))
    assert zeile["event"] == "auslieferung"
    assert zeile["tool"] == "context_pack"
    assert zeile["ids"][0] == "gotcha/fastmcp-lifespan"
    assert zeile["ranking"] == "keyword"
    assert "kunde" not in zeile and "projekt" not in zeile


def test_json_formatter_entfernt_verbotene_felder():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "m", None, None)
    record.felder = {"kunde": "wbai", "ok": 1}
    zeile = json.loads(JsonFormatter().format(record))
    assert zeile["ok"] == 1 and "kunde" not in zeile


def test_settings_from_env():
    with pytest.raises(ValueError):
        Settings.from_env({})
    s = Settings.from_env(
        {
            "BRAVO_KONTEXT_TOKEN": "t",
            "BRAVO_ALLOWED_HOSTS": "a.example, b.example",
            "GITHUB_APP_ID": "1",
            "GITHUB_APP_PRIVATE_KEY": "line1\\nline2",
            "GITHUB_APP_INSTALLATION_ID": "2",
        }
    )
    assert s.allowed_hosts == ["a.example", "b.example"]
    assert s.github_enabled and s.github_app_private_key == "line1\nline2"
    assert not Settings.from_env({"BRAVO_KONTEXT_TOKEN": "t"}).github_enabled
