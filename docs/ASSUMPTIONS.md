# Annahmen und offene Punkte

Der Lauf war unbeaufsichtigt; jede Entscheidung ohne Rückfrage steht hier.
Status: **entschieden** (im Code umgesetzt) oder **offen** (braucht Menschen/Admin-Rechte).

## Allgemein
| ID | Annahme / Punkt | Status |
|---|---|---|
| A-GEN-1 | PRs direkt gegen `main` statt über einen Integrationsbranch (Vorgabe HANDOFF). | entschieden |
| A-GEN-2 | Ein Branch und PR pro Slice. Die PRs sind gestapelt: S5 (`feature/s5-infra-stack`) bringt das gemeinsame Tooling, S6 baut auf S5 auf, S9 auf S6. Alle zielen auf `main`; bis S5 gemergt ist, zeigt der S6-Diff auch S5. Merge-Reihenfolge: S5 → S6 → S9. | entschieden |
| A-GEN-3 | Python 3.12 (devcontainer, CI, Dockerfile). Black/Ruff mit Zeilenlänge 100. | entschieden |
| A-GEN-4 | pre-commit-Hooks laufen als `language: system` gegen die gepinnten Versionen aus `requirements-dev.txt`, damit pre-commit, CI und `make verify` identisch prüfen und offline funktionieren. | entschieden |
| A-GEN-5 | Ein gemeinsames `.venv` im Repo-Root für Server, Infra und Werkzeuge; `requirements*.in` getrennt je Bereich. | entschieden |
| A-GEN-6 | Branch-Schutz für `main` (Pflicht-Check `verify`, PR Pflicht) braucht Admin-Rechte am Repo. | offen |

## S5 Infra
| ID | Annahme / Punkt | Status |
|---|---|---|
| A-INFRA-1 | Nur Code und Mock-Tests (`pulumi.runtime.set_mocks`). Kein `preview`, kein `up` in der Cloud session. | entschieden |
| A-INFRA-2 | RG `rg-wbai-bravo-proto` wird nur per Name referenziert; ihre ID wird aus Subscription (`getClientConfig`) und Name gebildet. Ein Test stellt sicher, dass keine `ResourceGroup` deklariert wird. | entschieden |
| A-INFRA-3 | Der Tag `owner` und die Budget-Empfänger kommen aus der Pulumi-Config `owner` (Pflicht, `config.require`). Die Adresse steht bewusst nicht im Code; ein Mensch setzt sie mit `pulumi config set owner … --stack proto` (Wert laut README/HANDOFF). | offen |
| A-INFRA-4 | Budget und Role Assignments unterstützen in Azure keine Tags; alle anderen Ressourcen tragen die fünf Pflicht-Tags (Test). | entschieden |
| A-INFRA-5 | Budget 50 in Abrechnungswährung der Subscription (angenommen EUR), Start 2026-12-01, Alerts bei 80 % Ist und 100 % Prognose. | entschieden |
| A-INFRA-6 | Container App startet mit Platzhalter-Image `mcr.microsoft.com/k8se/quickstart:latest`, weil die ACR vor dem ersten `up` leer ist. Registry-Zugriff per MI wird erst aktiv, wenn `image` auf `acrwbaibravoproto.azurecr.io/…` zeigt. | entschieden |
| A-INFRA-7 | Key Vault: RBAC, Soft Delete 7 Tage, Purge Protection aus (Prototyp, damit Aufräumen möglich bleibt). | entschieden |
| A-INFRA-8 | KV-Secret `bravo-kontext-token` muss vor dem ersten `up` existieren, sonst startet die Revision nicht. Anlegen braucht Rolle `Key Vault Secrets Officer`. | offen |
| A-INFRA-9 | Rolle `Storage Blob Data Contributor` auf `stwbaibravostateproto` für den Operator, danach `pulumi stack init proto` (Secrets-Provider: Vorschlag `passphrase`, alternativ `azurekeyvault://kv-wbai-bravo-proto…`) und `pulumi preview`. | offen |
| A-INFRA-10 | Role Assignments brauchen beim `up` `Microsoft.Authorization/roleAssignments/write` auf der RG (Owner oder User Access Administrator). | offen |
| A-INFRA-11 | Kostenschätzung bleibt unter 50 €/Monat: CAE Consumption mit min 0 Replicas, ACR Basic (~5 €), KV Standard (Cent-Bereich), Log Analytics nach Volumen. Kein Stopp-Kriterium ausgelöst. | entschieden |

## Repo-Hygiene
| ID | Annahme / Punkt | Status |
|---|---|---|
| A-REPO-1 | Commits laufen unter der neutralen Identität `Bravo Tracer Bullet <bravo-tracer-bullet@users.noreply.github.com>`. | entschieden |
| A-REPO-2 | Der verwaiste Remote-Branch `feature/s5-infra` (erster Push mit falscher Default-Autorenschaft, Löschen war aus der Session nicht erlaubt) soll von einem Menschen gelöscht werden. Gültiger S5-Branch: `feature/s5-infra-stack`. | offen |

## S6 Wissens-MCP
| ID | Annahme / Punkt | Status |
|---|---|---|
| A-S6-1 | `mcp>=1.20,<2` (gepinnt 1.x per `make compile`), FastMCP mit `stateless_http=True` und `json_response=True`: keine Server-Sessions, passt zu min 0 / max 1 Replica. Host-App ist Starlette; ihr Lifespan führt `session_manager.run()` aus. | entschieden |
| A-S6-2 | DNS-Rebinding-Schutz über `BRAVO_ALLOWED_HOSTS`. In Azure setzt der Pulumi-Stack den Wert auf `ca-wbai-bravo-kontext-proto.<defaultDomain der CAE>`; `*` schaltet die Prüfung ab. | entschieden |
| A-S6-3 | Ranking-Modell laut HANDOFF `claude-haiku-4-5-20251001`, konfigurierbar über `BRAVO_RANKING_MODEL`. Aktuelle Haiku-Generation wäre `claude-haiku-5-5`; Wechsel ist nur eine Env-Änderung. Ranking: bis zu `3 × max` Keyword-Kandidaten an Claude (nur id, typ, titel, beschreibung, tech, tags), Antwort als JSON `{"ids": [...]}`, unbekannte IDs werden verworfen; bei jedem Fehler Fallback auf Keyword-Reihenfolge. | entschieden |
| A-S6-4 | Keyword-Score: Titel 3, Beschreibung 2, Tech/Tags 3, Inhalt 1 je Begriff; Bonus 5 bei Tech-Überschneidung; Stoppwörter DE/EN, Begriffe ≥ 3 Zeichen, Bindestrich-Wörter zusätzlich zerlegt. | entschieden |
| A-S6-5 | Log-Zeilen enthalten IDs, Anzahl, Ranking-Art, Dauer, Filter, aber nicht den Aufgabentext (könnte vertrauliche Details enthalten). | entschieden |
| A-S6-6 | `context_pack` liefert den Inhalt mit, `search` und `related` nur Metadaten, `get` alles. `max` ist auf 25 begrenzt. | entschieden |
| A-S6-7 | `propose` setzt `kunde`/`projekt` aus `BRAVO_DEFAULT_KUNDE`/`BRAVO_DEFAULT_PROJEKT` (Standard `wbai`/`bravo`), validiert gegen das Schema und gibt beides nie zurück. Branch `feature/wissen-<slug>`, PR gegen `WISSEN_REF` (main), Beschreibung beginnt mit `[PROTOTYP]`. Existiert der Branch schon, kommt `status: abgelehnt` mit GitHub-Fehler zurück. | entschieden |
| A-S6-8 | Offline-Modus: `WISSEN_LOCAL_PATH` hat Vorrang für das Lesen. Ohne GitHub App ist `propose` gestubbt (`status: offline`, nichts wird geschrieben). | entschieden |
| A-S6-9 | `/notify` leitet nur Adaptive Cards im Format von `scripts/notify-teams.sh` weiter, deren erster Text mit `[PROTOTYP]` beginnt; max. 64 KB. Ohne `TEAMS_WEBHOOK_URL` antwortet es `202 noop`. | entschieden |
| A-S6-10 | Schema `eintrag.schema.json` als Kopie im Paket (eingefroren im Wissens-Repo), damit der Server offline validieren kann. | entschieden |
| A-S6-11 | Docker-Daemon war in der Session nicht verfügbar; das Image wird im CI-Job `verify` gebaut. Lokal per `make docker-build`. | entschieden |
| A-S6-12 | GitHub App A12 anlegen und in der Org installieren (Rechte: Contents RW, Pull requests RW, Issues RW auf wissen- und sample-Repo). | offen |
| A-S6-13 | KV-Secrets für `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY`, optional `ANTHROPIC_API_KEY` und `TEAMS_WEBHOOK_URL` anlegen und im Pulumi-Stack als weitere `secrets`/`env` der Container App ergänzen. Bewusst noch nicht im Stack, weil eine Revision mit fehlenden KV-Secrets nicht startet. | offen |
| A-S6-14 | Image nach `acrwbaibravoproto` pushen (`az acr build`) und Pulumi-Config `image` umstellen. | offen |
| A-S6-15 | Network secret der Cloud-Umgebung, das `Authorization: Bearer …` an Requests zur Container-App-URL hängt (siehe sample `notify-teams.sh`). | offen |

## S9 Vorschlags-Tools
| ID | Annahme / Punkt | Status |
|---|---|---|
| A-S9-1 | Der MCP kennt die aufrufende Person nicht (ein gemeinsames Bearer-Token). Deshalb gibt sie sich über den Parameter `autor` an (Kürzel oder GitHub-Handle, `^[a-z0-9][a-z0-9-]{1,38}$`). E-Mail-Adressen werden abgelehnt, weil das sample-Repo öffentlich ist. Keine Verifikation im Prototyp; für Produktion OAuth am MCP. | entschieden |
| A-S9-2 | Zuordnung Vorschlag → Person über den HTML-Kommentar `<!-- bravo-autor: <autor> -->` im Issue-Body. `antworten` und `status` arbeiten nur auf Issues mit diesem Marker; `antworten` nur für den eigenen `autor` und offene Issues. | entschieden |
| A-S9-3 | Rückfrage = offenes Issue mit Label `triage`, dessen letzter Kommentar nicht vom App-Bot (`BRAVO_BOT_LOGIN`, Standard `wbai-bravo-mcp-proto[bot]`) stammt. Fragen von `claude[bot]` aus `bravo-triage.yml` zählen damit als Rückfrage. | entschieden |
| A-S9-4 | Antworten laufen als Kommentar des App-Bots mit Präfix `**Antwort von <autor>**`; der Guard in `bravo-triage.yml` (sample) lässt `wbai-bravo-mcp-proto[bot]` zu, sodass die Antwort die Triage erneut auslöst. Der Login muss zum tatsächlichen Slug der GitHub App A12 passen. | offen |
| A-S9-5 | Phasen in `status`: geschlossen + `not_planned` → abgelehnt, geschlossen → erledigt, Label `ready` → bereit zur Umsetzung, Label `triage` → in Prüfung. Verknüpfte PRs werden im Prototyp nicht aufgelöst. | entschieden |
| A-S9-6 | Issue-Titel `Vorschlag: <titel>`, Body beginnt mit `[PROTOTYP]`. Listen sind auf 100 Issues/Kommentare begrenzt (keine Paginierung im Prototyp). | entschieden |
| A-S9-7 | Ohne GitHub App nutzen die Tools ein In-Memory-Backend (Daten gehen beim Neustart verloren, Antworten tragen `modus: offline`). | entschieden |
| A-S9-8 | Labels `triage` und `ready` müssen im sample-Repo existieren; die GitHub App braucht dort Issues RW. | offen |
