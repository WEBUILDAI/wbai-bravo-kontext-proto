import json
from types import SimpleNamespace

import pytest

from bravo_kontext.ranking import ClaudeRanker
from bravo_kontext.wissen import WissensDienst, slugify
from tests.conftest import FIXTURES, assert_kein_kunde_projekt

pytestmark = pytest.mark.anyio


class FakeMessages:
    def __init__(self, antwort: str | Exception):
        self.antwort = antwort
        self.aufrufe: list[dict] = []

    async def create(self, **kwargs):
        self.aufrufe.append(kwargs)
        if isinstance(self.antwort, Exception):
            raise self.antwort
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.antwort)])


def fake_ranker(antwort):
    messages = FakeMessages(antwort)
    return ClaudeRanker("x", "test-model", client=SimpleNamespace(messages=messages)), messages


async def test_context_pack_keyword_ohne_api_key(dienst):
    ergebnis = await dienst.context_pack("FastAPI Endpunkt mit Filter und Konfiguration")
    assert ergebnis["ranking"] == "keyword"
    ids = [e["id"] for e in ergebnis["eintraege"]]
    assert "learning/items-filter-leere-liste" in ids
    assert "standard/python-logging-alt" not in ids
    assert all("inhalt" in e for e in ergebnis["eintraege"])
    assert_kein_kunde_projekt(ergebnis)


async def test_context_pack_schliesst_abgelaufene_aus(dienst):
    ergebnis = await dienst.context_pack("logging standard python print", max=25)
    assert "standard/python-logging-alt" not in [e["id"] for e in ergebnis["eintraege"]]


async def test_context_pack_max(dienst):
    ergebnis = await dienst.context_pack("python fastapi mcp pulumi", max=2)
    assert len(ergebnis["eintraege"]) == 2


async def test_context_pack_mit_claude_ranking(settings):
    antwort = json.dumps({"ids": ["muster/fastapi-dependency-injection", "erfunden/id"]})
    ranker, messages = fake_ranker(antwort)
    from bravo_kontext.quelle import LokaleQuelle

    dienst = WissensDienst(settings, LokaleQuelle(FIXTURES), ranker=ranker)
    ergebnis = await dienst.context_pack("FastAPI Konfiguration testen", tech=["fastapi"])
    assert ergebnis["ranking"] == "claude"
    assert [e["id"] for e in ergebnis["eintraege"]] == ["muster/fastapi-dependency-injection"]
    gesendet = json.dumps(messages.aufrufe[0], default=str)
    assert "fixture-geheim" not in gesendet and "kunde" not in gesendet
    assert messages.aufrufe[0]["model"] == "test-model"


async def test_context_pack_fallback_bei_fehler(settings):
    from bravo_kontext.quelle import LokaleQuelle

    for antwort in (RuntimeError("down"), "kein json"):
        ranker, _ = fake_ranker(antwort)
        dienst = WissensDienst(settings, LokaleQuelle(FIXTURES), ranker=ranker)
        ergebnis = await dienst.context_pack("FastAPI Konfiguration")
        assert ergebnis["ranking"] == "keyword"
        assert ergebnis["eintraege"]


async def test_search_filter(dienst):
    alle = await dienst.search("")
    assert len(alle["treffer"]) == 4
    gotchas = await dienst.search("", typ="gotcha")
    assert [t["id"] for t in gotchas["treffer"]] == ["gotcha/fastmcp-lifespan"]
    pulumi = await dienst.search("backend", tech="pulumi")
    assert [t["id"] for t in pulumi["treffer"]] == ["entscheidung/pulumi-azblob-backend"]
    assert "inhalt" not in pulumi["treffer"][0]
    assert_kein_kunde_projekt(alle)


async def test_get(dienst):
    ok = await dienst.get("gotcha/fastmcp-lifespan")
    assert ok["eintrag"]["inhalt"].startswith("Wird")
    assert_kein_kunde_projekt(ok)
    assert "fehler" in await dienst.get("standard/python-logging-alt")
    assert "fehler" in await dienst.get("gibt/es-nicht")


async def test_related(dienst):
    ergebnis = await dienst.related("muster/fastapi-dependency-injection")
    ids = [v["id"] for v in ergebnis["verwandt"]]
    assert ids[0] == "learning/items-filter-leere-liste"
    assert "muster/fastapi-dependency-injection" not in ids
    assert "standard/python-logging-alt" not in ids
    assert "fehler" in await dienst.related("gibt/es-nicht")


async def test_propose_offline(dienst):
    ergebnis = await dienst.propose(
        "gotcha",
        "Uvicorn proxy_headers in Container Apps",
        "Relevant, wenn Container Apps hinter dem Envoy-Proxy läuft.",
        ["python", "uvicorn"],
        "proxy_headers=True setzen.",
    )
    assert ergebnis["status"] == "offline"
    assert ergebnis["branch"] == "feature/wissen-uvicorn-proxy-headers-in-container-apps"
    assert ergebnis["pfad"] == "eintraege/gotcha/uvicorn-proxy-headers-in-container-apps.md"
    assert_kein_kunde_projekt(ergebnis)


async def test_propose_validierung(dienst):
    assert (await dienst.propose("quatsch", "Titel ok", "Beschreibung ok", ["x"], "i"))[
        "status"
    ] == "abgelehnt"
    kurz = await dienst.propose("learning", "Kurz", "zu kurz", ["python"], "i")
    assert kurz["status"] == "abgelehnt"


class FakeGitHub:
    def __init__(self):
        self.aufrufe = []

    async def branch_sha(self, repo, branch):
        self.aufrufe.append(("sha", repo, branch))
        return "abc"

    async def create_branch(self, repo, branch, sha):
        self.aufrufe.append(("branch", repo, branch, sha))

    async def put_file(self, repo, branch, path, content, message):
        self.aufrufe.append(("file", repo, branch, path, content))

    async def create_pull(self, repo, head, base, title, body):
        self.aufrufe.append(("pr", repo, head, base, title, body))
        return {"html_url": "https://github.com/x/y/pull/7", "number": 7, "body": body}


async def test_propose_online(settings):
    from bravo_kontext.quelle import LokaleQuelle

    gh = FakeGitHub()
    dienst = WissensDienst(settings, LokaleQuelle(FIXTURES), github=gh)
    ergebnis = await dienst.propose(
        "learning",
        "Größe der Antwort begrenzen",
        "Relevant bei MCP-Tools mit großen Ergebnissen.",
        ["MCP"],
        "Max-Parameter anbieten.",
        tags=["Performance"],
    )
    assert ergebnis["status"] == "pr_erstellt" and ergebnis["pr"] == 7
    file_call = next(a for a in gh.aufrufe if a[0] == "file")
    assert file_call[2] == "feature/wissen-groesse-der-antwort-begrenzen"
    assert "kunde: wbai" in file_call[4] and "tech:\n- mcp" in file_call[4]
    pr_call = next(a for a in gh.aufrufe if a[0] == "pr")
    assert pr_call[5].startswith("[PROTOTYP]")
    assert pr_call[3] == "main"


def test_slugify():
    assert slugify("Ärger mit Übergrößen!") == "aerger-mit-uebergroessen"
    assert slugify("???") == "eintrag"
