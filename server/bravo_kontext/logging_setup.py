"""Strukturiertes Logging (eine JSON-Zeile pro Ereignis auf stdout).

Container Apps schreibt stdout nach Log Analytics (Tabelle ``ContainerAppConsoleLogs_CL``).
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from bravo_kontext.filter import redact

AUSLIEFERUNG_LOGGER = "bravo_kontext.auslieferung"


class JsonFormatter(logging.Formatter):
    """Formatiert Log-Records als einzeilige JSON-Objekte."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialisiert einen Record.

        Args:
            record: Der Log-Record. Felder aus ``extra={"felder": {...}}`` werden übernommen.

        Returns:
            JSON-Zeile.
        """
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        felder = getattr(record, "felder", None)
        if isinstance(felder, dict):
            payload.update(redact(felder))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_format: str = "json", level: str = "INFO") -> None:
    """Richtet das Root-Logging ein.

    Args:
        log_format: ``json`` für strukturierte Zeilen, sonst Klartext.
        level: Log-Level.
    """
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def log_auslieferung(tool: str, ids: list[str], **felder: Any) -> None:
    """Schreibt eine strukturierte Log-Zeile für eine Auslieferung.

    Args:
        tool: Name des MCP-Tools oder Endpunkts.
        ids: Ausgelieferte Eintrags-IDs.
        **felder: Weitere Felder (z. B. ``ranking``, ``dauer_ms``).
    """
    logging.getLogger(AUSLIEFERUNG_LOGGER).info(
        "auslieferung",
        extra={
            "felder": {"event": "auslieferung", "tool": tool, "ids": ids, "anzahl": len(ids)}
            | felder
        },
    )
