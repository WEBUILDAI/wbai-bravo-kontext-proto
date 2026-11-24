from datetime import date

import pytest

from bravo_kontext.eintraege import EintragFehler, lade_verzeichnis, parse_eintrag, render_eintrag
from tests.conftest import FIXTURES


def test_fixtures_sind_schemakonform():
    eintraege = lade_verzeichnis(FIXTURES)
    assert len(eintraege) == 5
    assert {e.kunde for e in eintraege} == {"wbai"}


def test_abgelaufen():
    eintraege = {e.id: e for e in lade_verzeichnis(FIXTURES)}
    assert eintraege["standard/python-logging-alt"].ist_abgelaufen()
    assert not eintraege["gotcha/fastmcp-lifespan"].ist_abgelaufen()
    assert not eintraege["standard/python-logging-alt"].ist_abgelaufen(date(2019, 1, 1))


def test_oeffentlich_ohne_kunde_projekt():
    for e in lade_verzeichnis(FIXTURES):
        sicht = e.oeffentlich()
        assert "kunde" not in sicht and "projekt" not in sicht
        assert sicht["id"] == e.id


def test_typ_muss_zum_ordner_passen():
    text = (FIXTURES / "eintraege/gotcha/fastmcp-lifespan.md").read_text()
    with pytest.raises(EintragFehler):
        parse_eintrag("muster/fastmcp-lifespan", text)


def test_ungueltiges_frontmatter_wird_uebersprungen(tmp_path):
    ordner = tmp_path / "eintraege" / "gotcha"
    ordner.mkdir(parents=True)
    (ordner / "kaputt.md").write_text("---\ntyp: gotcha\n---\nfehlt alles")
    (ordner / "ohne.md").write_text("kein frontmatter")
    assert lade_verzeichnis(tmp_path) == []
    assert lade_verzeichnis(tmp_path / "gibtsnicht") == []


def test_render_roundtrip():
    meta = {
        "typ": "learning",
        "titel": "Ein Titel für den Test",
        "beschreibung": "Relevant für den Roundtrip-Test.",
        "tech": ["python"],
        "tags": ["test"],
        "kunde": "wbai",
        "projekt": "bravo",
        "quelle": "https://example.org",
        "gueltig_bis": "2099-01-01",
    }
    text = render_eintrag(meta, "Inhalt")
    e = parse_eintrag("learning/ein-titel", text)
    assert e.titel == meta["titel"] and e.inhalt == "Inhalt"
    with pytest.raises(EintragFehler):
        render_eintrag(meta | {"quelle": "http://unsicher"}, "x")
