---
typ: learning
titel: Unbekannte Filterwerte liefern eine leere Liste statt 404
beschreibung: Relevant bei Listen-Endpunkten mit Query-Filtern in FastAPI.
tech: [python, fastapi]
tags: [api-design, filter]
kunde: wbai
projekt: fixture-geheim-beta
quelle: https://github.com/WEBUILDAI/wbai-bravo-sample-proto
gueltig_bis: 2099-12-31
---
`GET /items?category=unbekannt` gibt `[]` mit Status 200 zurück.
