# server – Bravo Wissens-MCP

> PROTOTYP, nonprod. Keine Kundendaten.

MCP-Server (offizielles Python SDK, `mcp<2`, FastMCP, Streamable HTTP, stateless, JSON-Antworten).
Liefert Claude-Sessions Kontext aus `wbai-bravo-wissen-proto` und nimmt Vorschläge an.

## Endpunkte
| Pfad | Auth | Zweck |
|---|---|---|
| `POST /mcp` | Bearer | MCP Streamable HTTP |
| `POST /notify` | Bearer | Relay für Teams-Karten aus `scripts/notify-teams.sh` (sample) an `TEAMS_WEBHOOK_URL` |
| `GET /healthz` | – | Liveness |

## Tools
| Tool | Zweck |
|---|---|
| `context_pack(aufgabe, tech?, max=10)` | Kandidaten per Keyword-Score, Ranking per Claude (`BRAVO_RANKING_MODEL`), ohne `ANTHROPIC_API_KEY` reiner Keyword-Score |
| `search(query, typ?, tech?)` | Keyword-Suche, Filter auf Typ/Technologie |
| `get(id)` | Eintrag vollständig (`<typ>/<slug>`) |
| `related(id, max=5)` | Verwandte Einträge über Tech, Tags und Begriffe |
| `propose(typ, titel, beschreibung, tech, inhalt, tags?, quelle?, gueltig_bis?)` | Branch `feature/wissen-<slug>` + PR im Wissens-Repo; offline gestubbt |
| `vorschlag_anlegen(titel, beschreibung, autor, kontext?)` | Issue mit Label `triage` im sample-Repo (S9) |
| `meine_rueckfragen(autor)` | Offene eigene Vorschläge, deren letzter Kommentar nicht vom MCP stammt |
| `antworten(issue, text, autor)` | Kommentar auf den eigenen Vorschlag (löst `bravo-triage.yml` erneut aus) |
| `status(issue)` | Phase (in Prüfung / bereit zur Umsetzung / erledigt / abgelehnt), Labels, letzte Kommentare |

Die Vorschlags-Tools arbeiten ohne GitHub App mit einem In-Memory-Backend (`modus: offline`).

Garantien (mit Tests):
- Abgelaufene Einträge (`gueltig_bis` < heute) werden nie ausgeliefert.
- `kunde` und `projekt` verlassen den Server nie (Whitelist in `Eintrag.oeffentlich`, rekursiver
  Filter `filter.redact` auf jeder Tool-Antwort und jeder Log-Zeile, Test über alle Tools per HTTP).
- Jede Auslieferung schreibt eine JSON-Zeile (`event=auslieferung`, `tool`, `ids`, `anzahl`, …) auf
  stdout → Container Apps → Log Analytics (`ContainerAppConsoleLogs_CL`).
- Bearer-Token mit `hmac.compare_digest`.

## Lokal
```bash
make install
make run            # Offline-Modus mit den Test-Fixtures, Token: lokal-nur-zum-testen
curl -s localhost:8000/mcp \
  -H "Authorization: Bearer lokal-nur-zum-testen" \
  -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"context_pack","arguments":{"aufgabe":"FastAPI Filter"}}}'
```
Eigener Klon: `WISSEN_LOCAL_PATH=../wbai-bravo-wissen-proto make run`. Alle Variablen: `.env.example`.

Claude Code (`.mcp.json` im sample-Repo):
```json
{"mcpServers": {"bravo-kontext": {"type": "http", "url": "${BRAVO_KONTEXT_URL}/mcp",
  "headers": {"Authorization": "Bearer ${BRAVO_KONTEXT_TOKEN}"}}}}
```

## Modi
| Konfiguration | Lesen | `propose` |
|---|---|---|
| `WISSEN_LOCAL_PATH` gesetzt | lokaler Klon (Vorrang) | GitHub App falls konfiguriert, sonst Stub |
| GitHub App (`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_APP_INSTALLATION_ID`) | Tarball von `WISSEN_REPO@WISSEN_REF`, Cache `BRAVO_CACHE_TTL` s | Branch + PR |
| nichts | keine Einträge (Warnung im Log) | Stub |

## Container
`make docker-build` (CI baut das Image im Job `verify`). Port 8000, User `app` (UID 10001).
