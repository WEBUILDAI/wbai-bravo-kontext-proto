import base64
import io
import json
import tarfile

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from bravo_kontext.github_app import GitHubApp, GitHubFehler
from bravo_kontext.quelle import GitHubQuelle
from tests.conftest import FIXTURES

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def schluessel():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return key, pem


def _tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(FIXTURES / "eintraege", arcname="WEBUILDAI-wissen-abc123/eintraege")
    return buf.getvalue()


def make_handler(schluessel, protokoll):
    key, _ = schluessel

    def handler(request: httpx.Request) -> httpx.Response:
        protokoll.append((request.method, request.url.path))
        auth = request.headers.get("authorization", "")
        if request.url.path == "/app/installations/42/access_tokens":
            claims = jwt.decode(auth.split()[1], key.public_key(), algorithms=["RS256"])
            assert claims["iss"] == "7"
            return httpx.Response(201, json={"token": "inst-token"})
        assert auth == "Bearer inst-token"
        if request.url.path.endswith("/tarball/main"):
            return httpx.Response(200, content=_tarball())
        if request.url.path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "abc"}})
        if request.url.path.endswith("/git/refs"):
            assert json.loads(request.content)["ref"] == "refs/heads/feature/x"
            return httpx.Response(201, json={})
        if "/contents/" in request.url.path:
            body = json.loads(request.content)
            assert base64.b64decode(body["content"]).decode() == "inhalt"
            return httpx.Response(201, json={})
        if request.url.path.endswith("/pulls"):
            return httpx.Response(201, json={"number": 3, "html_url": "u"})
        return httpx.Response(404, json={"message": "Not Found"})

    return handler


async def test_github_app_ablauf(schluessel):
    protokoll = []
    gh = GitHubApp(
        "7", schluessel[1], "42", transport=httpx.MockTransport(make_handler(schluessel, protokoll))
    )
    sha = await gh.branch_sha("o/r", "main")
    await gh.create_branch("o/r", "feature/x", sha)
    await gh.put_file("o/r", "feature/x", "a.md", "inhalt", "msg")
    pr = await gh.create_pull("o/r", "feature/x", "main", "t", "b")
    assert pr["number"] == 3
    # Installation-Token wird gecacht.
    assert protokoll.count(("POST", "/app/installations/42/access_tokens")) == 1
    with pytest.raises(GitHubFehler) as exc:
        await gh.request("GET", "/gibtsnicht")
    assert exc.value.status == 404


async def test_github_quelle_laedt_tarball(schluessel):
    protokoll = []
    gh = GitHubApp(
        "7", schluessel[1], "42", transport=httpx.MockTransport(make_handler(schluessel, protokoll))
    )
    quelle = GitHubQuelle(gh, "o/r", "main", ttl_seconds=300)
    eintraege = await quelle.eintraege()
    assert len(eintraege) == 5
    await quelle.eintraege()
    assert sum(1 for p in protokoll if p[1].endswith("/tarball/main")) == 1


async def test_github_quelle_fehler_liefert_alten_stand(schluessel):
    def handler(request):
        return httpx.Response(500, json={"message": "kaputt"})

    gh = GitHubApp("7", schluessel[1], "42", transport=httpx.MockTransport(handler))
    assert await GitHubQuelle(gh, "o/r", "main").eintraege() == []
