import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

import auth

ISS, AUD = "https://idp.example", "genome-lens"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJWKS:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


def mint(**over):
    now = int(time.time())
    claims = {"iss": ISS, "aud": AUD, "iat": now, "exp": now + 300, "email": "a@corp.com", "email_verified": True}
    claims.update(over)
    return jwt.encode(claims, KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("OIDC_AUDIENCE", AUD)
    monkeypatch.setattr(auth, "_jwks_client", lambda issuer: FakeJWKS())


def test_valid_token():
    assert auth.verify_token(mint())["email"] == "a@corp.com"


@pytest.mark.parametrize("over", [{"exp": 1}, {"aud": "other"}, {"iss": "https://evil"}])
def test_rejects_bad_claims(over):
    with pytest.raises(ValueError):
        auth.verify_token(mint(**over))


def test_rejects_wrong_signature():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    bad = jwt.encode({"iss": ISS, "aud": AUD, "iat": now, "exp": now + 60}, other, algorithm="RS256")
    with pytest.raises(ValueError):
        auth.verify_token(bad)


def test_domain_allowlist(monkeypatch):
    monkeypatch.setenv("AUTH_ALLOWED_EMAIL_DOMAINS", "corp.com")
    auth.verify_token(mint())
    with pytest.raises(ValueError):
        auth.verify_token(mint(email="a@gmail.com"))
    with pytest.raises(ValueError):
        auth.verify_token(mint(email_verified=False))


def test_rest_dependency_and_disabled(monkeypatch):
    app = FastAPI()
    app.get("/x")(lambda u=Depends(auth.require_user): {"ok": True})
    c = TestClient(app)
    assert c.get("/x").status_code == 401
    assert c.get("/x", headers={"Authorization": f"Bearer {mint()}"}).status_code == 200
    monkeypatch.setenv("AUTH_ENABLED", "false")
    assert c.get("/x").status_code == 200
