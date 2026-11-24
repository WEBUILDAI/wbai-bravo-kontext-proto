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
