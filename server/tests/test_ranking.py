from bravo_kontext.eintraege import lade_verzeichnis
from bravo_kontext.ranking import nach_keyword, tokens
from tests.conftest import FIXTURES


def test_tokens_ohne_stoppworte():
    assert tokens("Der FastAPI-Endpunkt und die Filter") == {
        "fastapi-endpunkt",
        "fastapi",
        "endpunkt",
        "filter",
    }


def test_keyword_ranking_bevorzugt_passende_eintraege():
    eintraege = lade_verzeichnis(FIXTURES)
    ergebnis = nach_keyword(eintraege, "FastMCP lifespan in Starlette mounten")
    assert ergebnis[0][0].id == "gotcha/fastmcp-lifespan"


def test_tech_bonus():
    eintraege = lade_verzeichnis(FIXTURES)
    ids = [e.id for e, _ in nach_keyword(eintraege, "state backend", tech=["pulumi"])]
    assert ids[0] == "entscheidung/pulumi-azblob-backend"


def test_kein_treffer():
    assert nach_keyword(lade_verzeichnis(FIXTURES), "kubernetes helm") == []
