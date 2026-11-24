"""Gemeinsame Fixtures für die Server-Tests."""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from bravo_kontext.app import create_app
from bravo_kontext.config import Settings
from bravo_kontext.quelle import LokaleQuelle
from bravo_kontext.wissen import WissensDienst

FIXTURES = Path(__file__).parent / "fixtures" / "wissen"
TOKEN = "test-token-nicht-geheim"
GEHEIM = ("fixture-geheim", "kunde", "projekt")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        token=TOKEN,
        allowed_hosts=["testserver", "localhost:*"],
        wissen_local_path=FIXTURES,
    )


@pytest.fixture
def dienst(settings) -> WissensDienst:
    return WissensDienst(settings, LokaleQuelle(FIXTURES))


@pytest.fixture
def client(settings, dienst):
    with TestClient(create_app(settings, dienst)) as c:
        yield c


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def mcp_headers() -> dict[str, str]:
    return auth() | {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }


def call_tool(client, name: str, arguments: dict) -> dict:
    resp = client.post(
        "/mcp",
        headers=mcp_headers(),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert not result.get("isError"), result
    return result


def assert_kein_kunde_projekt(obj) -> None:
    """Prüft rekursiv, dass weder Schlüssel noch Werte kunde/projekt verraten."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in ("kunde", "projekt"), obj
            assert_kein_kunde_projekt(v)
    elif isinstance(obj, list):
        for v in obj:
            assert_kein_kunde_projekt(v)
    elif isinstance(obj, str):
        assert "fixture-geheim" not in obj
