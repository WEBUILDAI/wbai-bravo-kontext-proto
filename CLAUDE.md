# CLAUDE.md – wbai-bravo-kontext-proto

> PROTOTYP, nonprod. Keine Kundendaten, keine Secrets, Ablauf 2027-02-24.

## Was hier liegt
- `server/`: Wissens-MCP (`bravo_kontext`), FastMCP Streamable HTTP, Tests mit Fixture-Einträgen
  unter `server/tests/fixtures/wissen/`. Details: `server/README.md`.
- `infra/`: Pulumi (Python), Stack `proto`, Backend `azblob://pulumi-state?storage_account=stwbaibravostateproto`.
  Bestehende RG `rg-wbai-bravo-proto` wird nur referenziert.
- `docs/HANDOFF.md`: Auftrag und Slices (gleich in allen drei Bravo-Repos).
- `docs/ASSUMPTIONS.md`: jede Annahme und jeder offene Admin-Schritt.

## Arbeitsweise
- Vor jedem Commit: `make verify` (Ruff, Black, pytest). CI-Job heißt `verify`.
- Abhängigkeiten nur in `requirements*.in` ändern, dann `make compile`.
- Python 3.12, Google-Docstrings, `logging` statt `print`.
- Branches `feature/…`, `bugfix/…`, `chore/…`; PRs gegen `main`, Beschreibung beginnt mit `[PROTOTYP]`.
- Neue Annahmen sofort in `docs/ASSUMPTIONS.md` (mit ID und Status `offen`/`entschieden`).

## Server-Regeln
- `kunde` und `projekt` nie ausgeben: neue Felder nur über `Eintrag.oeffentlich()`, Antworten
  durch `filter.redact`. Der Test `test_kein_kunde_projekt_in_allen_tools` muss jedes Tool abdecken.
- Abgelaufene Einträge nie ausliefern (`WissensDienst._gueltige`).
- Jede Auslieferung über `log_auslieferung` loggen.
- Das Schema `server/bravo_kontext/schema/eintrag.schema.json` ist eine Kopie aus dem Wissens-Repo
  und eingefroren; nur dort ändern, dann hierher kopieren.
- Lokal starten: `make run` (Offline-Modus, Fixtures).

## Nie
- Secrets committen (Tokens, Keys, `.env`). Werte kommen aus Key Vault bzw. Umgebung.
- `pulumi up`, `pulumi destroy`, Azure-Ressourcen anlegen oder löschen. Nur Code und Mock-Tests;
  `pulumi preview` nur lokal durch einen Menschen.
- Die Resource Group anlegen oder ändern.
- Mergen oder force-pushen.
- Hinweise auf KI-Werkzeuge, Co-Authored-By oder Session-Links in Commits/PRs.

## Pflicht-Tags (Azure)
`environment=nonprod`, `stage=prototype`, `project=bravo`, `owner=<Pulumi-Config owner>`,
`expires=2027-02-24`. Zentral in `infra/bravo_infra/tags.py`, Test prüft alle Ressourcen.
