"""Konfiguration aus Umgebungsvariablen."""

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_RANKING_MODEL = "claude-haiku-4-5-20251001"


def _csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [part.strip() for part in value.split(",") if part.strip()]


@dataclass(frozen=True)
class Settings:
    """Laufzeit-Konfiguration des Servers.

    Attributes:
        token: Bearer-Token für alle geschützten Endpunkte (``BRAVO_KONTEXT_TOKEN``).
        allowed_hosts: Erlaubte Host-Header für den MCP-Transport. ``*`` schaltet die
            DNS-Rebinding-Prüfung ab.
        wissen_local_path: Lokaler Klon des Wissens-Repos (Offline-Modus).
        wissen_repo: ``owner/repo`` des Wissens-Repos.
        wissen_ref: Branch, aus dem gelesen und gegen den Vorschläge gestellt werden.
        sample_repo: ``owner/repo`` für Änderungsvorschläge (S9).
        github_app_id: ID der GitHub App.
        github_app_private_key: Privater Schlüssel der GitHub App (PEM).
        github_app_installation_id: Installation der App in der Organisation.
        anthropic_api_key: Optionaler API-Key für das Ranking per Claude.
        ranking_model: Modell für das Ranking in ``context_pack``.
        teams_webhook_url: Ziel für ``POST /notify``.
        cache_ttl_seconds: Wie lange Einträge aus GitHub gecacht werden.
        default_kunde: ``kunde`` für neue Vorschläge (nur Metadatum).
        default_projekt: ``projekt`` für neue Vorschläge (nur Metadatum).
        bot_login: Login der GitHub App als Kommentar-Autor (``<slug>[bot]``).
        log_format: ``json`` oder ``text``.
        log_level: Python-Log-Level.
    """

    token: str
    allowed_hosts: list[str] = field(default_factory=lambda: ["localhost:*", "127.0.0.1:*"])
    wissen_local_path: Path | None = None
    wissen_repo: str = "WEBUILDAI/wbai-bravo-wissen-proto"
    wissen_ref: str = "main"
    sample_repo: str = "WEBUILDAI/wbai-bravo-sample-proto"
    github_app_id: str | None = None
    github_app_private_key: str | None = None
    github_app_installation_id: str | None = None
    anthropic_api_key: str | None = None
    ranking_model: str = DEFAULT_RANKING_MODEL
    teams_webhook_url: str | None = None
    cache_ttl_seconds: int = 300
    default_kunde: str = "wbai"
    default_projekt: str = "bravo"
    bot_login: str = "wbai-bravo-mcp-proto[bot]"
    log_format: str = "json"
    log_level: str = "INFO"

    @property
    def github_enabled(self) -> bool:
        """Ob alle Angaben für die GitHub App vorhanden sind."""
        return bool(
            self.github_app_id and self.github_app_private_key and self.github_app_installation_id
        )

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        """Liest die Konfiguration aus Umgebungsvariablen.

        Args:
            env: Optionales Mapping statt ``os.environ`` (für Tests).

        Returns:
            Fertige Settings.

        Raises:
            ValueError: Wenn ``BRAVO_KONTEXT_TOKEN`` fehlt.
        """
        e = os.environ if env is None else env
        token = e.get("BRAVO_KONTEXT_TOKEN", "")
        if not token:
            raise ValueError("BRAVO_KONTEXT_TOKEN ist nicht gesetzt")
        local = e.get("WISSEN_LOCAL_PATH")
        private_key = e.get("GITHUB_APP_PRIVATE_KEY")
        if private_key:
            # In Env-Variablen werden Zeilenumbrüche oft als \n übergeben.
            private_key = private_key.replace("\\n", "\n")
        return cls(
            token=token,
            allowed_hosts=_csv(e.get("BRAVO_ALLOWED_HOSTS"), ["localhost:*", "127.0.0.1:*"]),
            wissen_local_path=Path(local) if local else None,
            wissen_repo=e.get("WISSEN_REPO", cls.wissen_repo),
            wissen_ref=e.get("WISSEN_REF", cls.wissen_ref),
            sample_repo=e.get("SAMPLE_REPO", cls.sample_repo),
            github_app_id=e.get("GITHUB_APP_ID") or None,
            github_app_private_key=private_key or None,
            github_app_installation_id=e.get("GITHUB_APP_INSTALLATION_ID") or None,
            anthropic_api_key=e.get("ANTHROPIC_API_KEY") or None,
            ranking_model=e.get("BRAVO_RANKING_MODEL", DEFAULT_RANKING_MODEL),
            teams_webhook_url=e.get("TEAMS_WEBHOOK_URL") or None,
            cache_ttl_seconds=int(e.get("BRAVO_CACHE_TTL", "300")),
            default_kunde=e.get("BRAVO_DEFAULT_KUNDE", "wbai"),
            default_projekt=e.get("BRAVO_DEFAULT_PROJEKT", "bravo"),
            bot_login=e.get("BRAVO_BOT_LOGIN", cls.bot_login),
            log_format=e.get("LOG_FORMAT", "json"),
            log_level=e.get("LOG_LEVEL", "INFO"),
        )
