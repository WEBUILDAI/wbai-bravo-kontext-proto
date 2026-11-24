---
typ: gotcha
titel: FastMCP Streamable HTTP braucht den Session-Manager im Host-Lifespan
beschreibung: Relevant, wenn ein FastMCP-Server in eine eigene Starlette- oder FastAPI-App gemountet wird.
tech: [python, mcp, starlette]
tags: [lifespan, streamable-http]
kunde: wbai
projekt: fixture-geheim-alpha
quelle: https://github.com/WEBUILDAI/wbai-bravo-wissen-proto
gueltig_bis: 2099-12-31
---
Wird `streamable_http_app()` gemountet, muss der Lifespan der Host-App
`session_manager.run()` ausführen, sonst schlagen alle Requests mit
"Task group is not initialized" fehl.
