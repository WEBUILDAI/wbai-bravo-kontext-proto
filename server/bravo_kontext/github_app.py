"""Schlanker GitHub-Client über eine GitHub App (Installation-Token)."""

import base64
import logging
import time
from typing import Any

import httpx
import jwt

logger = logging.getLogger(__name__)

API = "https://api.github.com"


class GitHubFehler(RuntimeError):
    """Fehler bei einem GitHub-API-Aufruf.

    Attributes:
        status: HTTP-Status der Antwort.
    """

    def __init__(self, status: int, nachricht: str) -> None:
        super().__init__(f"GitHub {status}: {nachricht}")
        self.status = status


class GitHubApp:
    """GitHub-REST-Client, authentifiziert als App-Installation.

    Args:
        app_id: ID der GitHub App.
        private_key: PEM des privaten App-Schlüssels.
        installation_id: Installation in der Organisation.
        transport: Optionaler httpx-Transport (für Tests).
    """

    def __init__(
        self,
        app_id: str,
        private_key: str,
        installation_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._transport = transport
        self._token: str | None = None
        self._token_ablauf = 0.0

    def _app_jwt(self) -> str:
        jetzt = int(time.time())
        claims = {"iat": jetzt - 60, "exp": jetzt + 540, "iss": self._app_id}
        return jwt.encode(claims, self._private_key, algorithm="RS256")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=API,
            transport=self._transport,
            timeout=20.0,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            follow_redirects=True,
        )

    async def _installation_token(self) -> str:
        if self._token and time.time() < self._token_ablauf - 60:
            return self._token
        async with self._client() as client:
            resp = await client.post(
                f"/app/installations/{self._installation_id}/access_tokens",
                headers={"Authorization": f"Bearer {self._app_jwt()}"},
            )
        if resp.status_code != 201:
            raise GitHubFehler(resp.status_code, "Installation-Token nicht erhalten")
        daten = resp.json()
        self._token = daten["token"]
        # Token gilt eine Stunde; konservativ 55 Minuten cachen.
        self._token_ablauf = time.time() + 55 * 60
        return self._token

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Führt einen authentifizierten API-Aufruf aus.

        Args:
            method: HTTP-Methode.
            path: Pfad relativ zu ``https://api.github.com``.
            **kwargs: Weitere Argumente für ``httpx.AsyncClient.request``.

        Returns:
            Die Antwort.

        Raises:
            GitHubFehler: Bei Status >= 400.
        """
        token = await self._installation_token()
        async with self._client() as client:
            resp = await client.request(
                method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
        if resp.status_code >= 400:
            try:
                nachricht = resp.json().get("message", resp.text)
            except ValueError:
                nachricht = resp.text
            raise GitHubFehler(resp.status_code, nachricht)
        return resp

    async def tarball(self, repo: str, ref: str) -> bytes:
        """Lädt das Repo als tar.gz.

        Args:
            repo: ``owner/repo``.
            ref: Branch oder SHA.

        Returns:
            Archiv-Bytes.
        """
        resp = await self.request("GET", f"/repos/{repo}/tarball/{ref}")
        return resp.content

    async def branch_sha(self, repo: str, branch: str) -> str:
        """Gibt den Head-SHA eines Branches zurück.

        Args:
            repo: ``owner/repo``.
            branch: Branch-Name.

        Returns:
            Commit-SHA.
        """
        resp = await self.request("GET", f"/repos/{repo}/git/ref/heads/{branch}")
        return resp.json()["object"]["sha"]

    async def create_branch(self, repo: str, branch: str, sha: str) -> None:
        """Legt einen Branch an.

        Args:
            repo: ``owner/repo``.
            branch: Neuer Branch-Name.
            sha: Ausgangs-Commit.
        """
        await self.request(
            "POST", f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha}
        )

    async def put_file(self, repo: str, branch: str, path: str, content: str, message: str) -> None:
        """Legt eine Datei auf einem Branch an.

        Args:
            repo: ``owner/repo``.
            branch: Ziel-Branch.
            path: Dateipfad im Repo.
            content: Dateiinhalt (UTF-8).
            message: Commit-Nachricht.
        """
        await self.request(
            "PUT",
            f"/repos/{repo}/contents/{path}",
            json={
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch,
            },
        )

    async def create_pull(
        self, repo: str, head: str, base: str, title: str, body: str
    ) -> dict[str, Any]:
        """Öffnet einen Pull Request.

        Args:
            repo: ``owner/repo``.
            head: Quell-Branch.
            base: Ziel-Branch.
            title: Titel.
            body: Beschreibung.

        Returns:
            PR-Objekt der API.
        """
        resp = await self.request(
            "POST",
            f"/repos/{repo}/pulls",
            json={"head": head, "base": base, "title": title, "body": body},
        )
        return resp.json()

    async def create_issue(
        self, repo: str, title: str, body: str, labels: list[str]
    ) -> dict[str, Any]:
        """Legt ein Issue an.

        Args:
            repo: ``owner/repo``.
            title: Titel.
            body: Beschreibung.
            labels: Labels.

        Returns:
            Issue-Objekt der API.
        """
        resp = await self.request(
            "POST", f"/repos/{repo}/issues", json={"title": title, "body": body, "labels": labels}
        )
        return resp.json()

    async def list_issues(self, repo: str, labels: list[str], state: str = "open") -> list[dict]:
        """Listet Issues (ohne Pull Requests) mit allen angegebenen Labels.

        Args:
            repo: ``owner/repo``.
            labels: Labels, die alle gesetzt sein müssen.
            state: ``open``, ``closed`` oder ``all``.

        Returns:
            Liste von Issue-Objekten (höchstens 100).
        """
        resp = await self.request(
            "GET",
            f"/repos/{repo}/issues",
            params={"labels": ",".join(labels), "state": state, "per_page": 100},
        )
        return [i for i in resp.json() if "pull_request" not in i]

    async def get_issue(self, repo: str, number: int) -> dict[str, Any]:
        """Liest ein Issue.

        Args:
            repo: ``owner/repo``.
            number: Issue-Nummer.

        Returns:
            Issue-Objekt der API.
        """
        resp = await self.request("GET", f"/repos/{repo}/issues/{number}")
        return resp.json()

    async def list_comments(self, repo: str, number: int) -> list[dict]:
        """Listet die Kommentare eines Issues (älteste zuerst, höchstens 100).

        Args:
            repo: ``owner/repo``.
            number: Issue-Nummer.

        Returns:
            Liste von Kommentar-Objekten.
        """
        resp = await self.request(
            "GET", f"/repos/{repo}/issues/{number}/comments", params={"per_page": 100}
        )
        return resp.json()

    async def create_comment(self, repo: str, number: int, body: str) -> dict[str, Any]:
        """Kommentiert ein Issue.

        Args:
            repo: ``owner/repo``.
            number: Issue-Nummer.
            body: Kommentartext.

        Returns:
            Kommentar-Objekt der API.
        """
        resp = await self.request(
            "POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body}
        )
        return resp.json()
