---
typ: entscheidung
titel: Pulumi-State liegt im Azure-Blob-Backend statt Pulumi Cloud
beschreibung: Relevant bei neuer Azure-Infrastruktur mit Pulumi und der Frage nach dem State-Backend.
tech: [pulumi, azure]
tags: [infrastruktur, state]
kunde: wbai
projekt: fixture-geheim-beta
quelle: https://github.com/WEBUILDAI/wbai-bravo-kontext-proto
gueltig_bis: 2099-12-31
---
State in `azblob://pulumi-state`, Zugriff per Entra-Rolle
`Storage Blob Data Contributor`. Keine Pulumi-Cloud-Lizenz nötig.
