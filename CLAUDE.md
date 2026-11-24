# CLAUDE.md – wbai-bravo-kontext-proto

> PROTOTYP, nonprod. Keine Kundendaten, keine Secrets, Ablauf 2027-02-24.

## Was hier liegt
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
