---
typ: muster
titel: Konfiguration in FastAPI per Dependency statt globaler Variablen
beschreibung: Relevant beim Aufbau neuer FastAPI-Endpunkte, die Settings oder Clients brauchen.
tech: [python, fastapi]
tags: [konfiguration, testbarkeit]
kunde: wbai
projekt: fixture-geheim-alpha
quelle: https://github.com/WEBUILDAI/wbai-bravo-sample-proto
gueltig_bis: 2099-12-31
---
Settings über `Depends(get_settings)` injizieren; in Tests per
`app.dependency_overrides` ersetzen.
