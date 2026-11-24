"""Fachlogik der Wissens-Tools (unabhängig vom MCP-Transport)."""

import logging
import re
import time
from datetime import date, timedelta
from typing import Any

from bravo_kontext.config import Settings
from bravo_kontext.eintraege import TYPEN, Eintrag, EintragFehler, render_eintrag
from bravo_kontext.filter import redact
from bravo_kontext.github_app import GitHubApp, GitHubFehler
from bravo_kontext.logging_setup import log_auslieferung
from bravo_kontext.quelle import WissenQuelle
from bravo_kontext.ranking import Ranker, keyword_score, nach_keyword, tokens

logger = logging.getLogger(__name__)

MAX_LIMIT = 25
KANDIDATEN_FAKTOR = 3
_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def slugify(text: str, max_len: int = 60) -> str:
    """Erzeugt einen Datei- und Branch-tauglichen Slug.

    Args:
        text: Ausgangstext, z. B. der Titel.
        max_len: Maximale Länge.

    Returns:
        Slug aus ``[a-z0-9-]``.
    """
    s = text.lower().translate(_UMLAUTE)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len].rstrip("-") or "eintrag"


class WissensDienst:
    """Implementiert ``context_pack``, ``search``, ``get``, ``related`` und ``propose``.

    Args:
        settings: Konfiguration.
        quelle: Quelle der Einträge.
        ranker: Optionaler Claude-Ranker; ohne ihn reiner Keyword-Score.
        github: Optionaler GitHub-Client; ohne ihn ist ``propose`` gestubbt.
    """

    def __init__(
        self,
        settings: Settings,
        quelle: WissenQuelle,
        ranker: Ranker | None = None,
        github: GitHubApp | None = None,
    ) -> None:
        self.settings = settings
        self.quelle = quelle
        self.ranker = ranker
        self.github = github

    async def _gueltige(self) -> list[Eintrag]:
        heute = date.today()
        return [e for e in await self.quelle.eintraege() if not e.ist_abgelaufen(heute)]

    async def context_pack(
        self, aufgabe: str, tech: list[str] | None = None, max: int = 10  # noqa: A002
    ) -> dict[str, Any]:
        """Stellt passenden Kontext für eine Aufgabe zusammen.

        Args:
            aufgabe: Beschreibung der Aufgabe.
            tech: Bevorzugte Technologien.
            max: Maximale Anzahl Einträge (1–25).

        Returns:
            Dict mit ``eintraege`` (inkl. Inhalt) und ``ranking`` (``claude`` oder ``keyword``).
        """
        start = time.perf_counter()
        limit = min(MAX_LIMIT, (max if max > 0 else 10))
        tech = tech or []
        kandidaten = [e for e, _ in nach_keyword(await self._gueltige(), aufgabe, tech)]
        kandidaten = kandidaten[: limit * KANDIDATEN_FAKTOR]
        ranking = "keyword"
        auswahl = kandidaten[:limit]
        if self.ranker and kandidaten:
            try:
                ids = await self.ranker.rank(aufgabe, kandidaten, limit)
                nach_id = {e.id: e for e in kandidaten}
                auswahl = [nach_id[i] for i in ids]
                ranking = "claude"
            except Exception:
                logger.warning("Ranking per Claude fehlgeschlagen, nutze Keyword-Score")
        ids = [e.id for e in auswahl]
        log_auslieferung(
            "context_pack",
            ids,
            ranking=ranking,
            kandidaten=len(kandidaten),
            tech=tech,
            dauer_ms=round((time.perf_counter() - start) * 1000),
        )
        return redact({"eintraege": [e.oeffentlich() for e in auswahl], "ranking": ranking})

    async def search(
        self, query: str, typ: str | None = None, tech: str | None = None
    ) -> dict[str, Any]:
        """Sucht Einträge per Keyword.

        Args:
            query: Suchtext.
            typ: Optionaler Filter auf den Typ.
            tech: Optionaler Filter auf eine Technologie.

        Returns:
            Dict mit ``treffer`` (ohne Inhalt, mit ``score``).
        """
        eintraege = await self._gueltige()
        if typ:
            eintraege = [e for e in eintraege if e.typ == typ]
        if tech:
            eintraege = [e for e in eintraege if tech.lower() in {t.lower() for t in e.tech}]
        if tokens(query):
            bewertet = nach_keyword(eintraege, query)
        else:
            bewertet = [(e, 0) for e in sorted(eintraege, key=lambda e: e.id)]
        treffer = [e.oeffentlich(mit_inhalt=False) | {"score": s} for e, s in bewertet]
        log_auslieferung("search", [t["id"] for t in treffer], typ=typ, tech=tech)
        return redact({"treffer": treffer})

    async def get(self, id: str) -> dict[str, Any]:  # noqa: A002
        """Liefert einen Eintrag vollständig.

        Args:
            id: ``<typ>/<slug>``.

        Returns:
            Dict mit ``eintrag`` oder ``fehler``.
        """
        for e in await self._gueltige():
            if e.id == id:
                log_auslieferung("get", [e.id])
                return redact({"eintrag": e.oeffentlich()})
        log_auslieferung("get", [])
        return {"fehler": f"Eintrag '{id}' nicht gefunden oder abgelaufen"}

    async def related(self, id: str, max: int = 5) -> dict[str, Any]:  # noqa: A002
        """Findet verwandte Einträge über gemeinsame Technologien, Tags und Begriffe.

        Args:
            id: Ausgangseintrag.
            max: Maximale Anzahl.

        Returns:
            Dict mit ``verwandt`` (ohne Inhalt) oder ``fehler``.
        """
        eintraege = await self._gueltige()
        basis = next((e for e in eintraege if e.id == id), None)
        if basis is None:
            log_auslieferung("related", [])
            return {"fehler": f"Eintrag '{id}' nicht gefunden oder abgelaufen"}
        begriffe = tokens(f"{basis.titel} {basis.beschreibung} {' '.join(basis.tags)}")
        bewertet = []
        for e in eintraege:
            if e.id == basis.id:
                continue
            gemeinsam = len(set(basis.tech) & set(e.tech)) * 2 + len(set(basis.tags) & set(e.tags))
            score = gemeinsam * 3 + keyword_score(e, begriffe)
            if gemeinsam or score:
                bewertet.append((e, score))
        bewertet.sort(key=lambda es: (-es[1], es[0].id))
        verwandt = [e.oeffentlich(mit_inhalt=False) for e, _ in bewertet[: min(max, MAX_LIMIT)]]
        log_auslieferung("related", [v["id"] for v in verwandt], basis=id)
        return redact({"verwandt": verwandt})

    async def propose(
        self,
        typ: str,
        titel: str,
        beschreibung: str,
        tech: list[str],
        inhalt: str,
        tags: list[str] | None = None,
        quelle: str | None = None,
        gueltig_bis: str | None = None,
    ) -> dict[str, Any]:
        """Schlägt einen neuen Eintrag als PR im Wissens-Repo vor.

        Args:
            typ: Einer von ``entscheidung``, ``learning``, ``muster``, ``gotcha``, ``standard``.
            titel: Titel (5–120 Zeichen).
            beschreibung: Ein Satz, wann der Eintrag relevant ist (10–300 Zeichen).
            tech: Technologien (klein, z. B. ``python``).
            inhalt: Markdown-Inhalt.
            tags: Schlagworte.
            quelle: HTTPS-URL der Quelle; Standard ist das Wissens-Repo.
            gueltig_bis: ISO-Datum; Standard heute + 365 Tage.

        Returns:
            Dict mit ``status`` (``pr_erstellt``, ``offline`` oder ``abgelehnt``) und Details.
        """
        if typ not in TYPEN:
            return {"status": "abgelehnt", "fehler": f"typ muss einer von {list(TYPEN)} sein"}
        slug = slugify(titel)
        pfad = f"eintraege/{typ}/{slug}.md"
        branch = f"feature/wissen-{slug}"
        meta = {
            "typ": typ,
            "titel": titel,
            "beschreibung": beschreibung,
            "tech": [t.lower() for t in tech],
            "tags": [t.lower() for t in (tags or [])],
            "kunde": self.settings.default_kunde,
            "projekt": self.settings.default_projekt,
            "quelle": quelle or f"https://github.com/{self.settings.wissen_repo}",
            "gueltig_bis": gueltig_bis or (date.today() + timedelta(days=365)).isoformat(),
        }
        try:
            datei = render_eintrag(meta, inhalt)
        except EintragFehler as exc:
            return {"status": "abgelehnt", "fehler": str(exc)}

        ergebnis: dict[str, Any] = {"id": f"{typ}/{slug}", "pfad": pfad, "branch": branch}
        if self.github is None:
            ergebnis |= {
                "status": "offline",
                "hinweis": "Keine GitHub App konfiguriert, Vorschlag wurde nicht eingereicht.",
            }
            log_auslieferung("propose", [], status="offline", vorschlag=ergebnis["id"])
            return redact(ergebnis)

        repo, base = self.settings.wissen_repo, self.settings.wissen_ref
        try:
            sha = await self.github.branch_sha(repo, base)
            await self.github.create_branch(repo, branch, sha)
            await self.github.put_file(repo, branch, pfad, datei, f"wissen: {titel}")
            pr = await self.github.create_pull(
                repo,
                head=branch,
                base=base,
                title=f"Wissen: {titel}",
                body=(
                    "[PROTOTYP] Vorschlag über den Wissens-MCP (`propose`).\n\n"
                    f"- Eintrag: `{pfad}`\n- Typ: {typ}\n- Beschreibung: {beschreibung}\n"
                ),
            )
        except GitHubFehler as exc:
            logger.warning("propose fehlgeschlagen: %s", exc)
            return {"status": "abgelehnt", "fehler": str(exc)} | ergebnis
        ergebnis |= {"status": "pr_erstellt", "pr_url": pr.get("html_url"), "pr": pr.get("number")}
        log_auslieferung("propose", [], status="pr_erstellt", vorschlag=ergebnis["id"])
        return redact(ergebnis)
