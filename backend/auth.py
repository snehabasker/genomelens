"""Optional OIDC bearer-token authentication.

Off by default. Set AUTH_ENABLED=true plus OIDC_ISSUER / OIDC_AUDIENCE to require a valid ID/access token
(JWT) from any standards-compliant provider - Google, Okta, Entra ID, Keycloak, Auth0. Signing keys come from
the issuer's JWKS endpoint (discovered via /.well-known/openid-configuration) and are cached by PyJWT.

Browsers cannot set headers on a WebSocket, so /ws also accepts the token as ?token=<jwt>.
"""
import os
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request, WebSocket
from jwt import PyJWKClient

import httpx


def enabled() -> bool:
    return os.getenv("AUTH_ENABLED", "false").lower() in ("1", "true", "yes")


def _allowed_domains() -> set[str]:
    return {d.strip().lower() for d in os.getenv("AUTH_ALLOWED_EMAIL_DOMAINS", "").split(",") if d.strip()}


@lru_cache(maxsize=4)
def _jwks_client(issuer: str) -> PyJWKClient:
    conf = httpx.get(f"{issuer.rstrip('/')}/.well-known/openid-configuration", timeout=5).raise_for_status().json()
    return PyJWKClient(conf["jwks_uri"], cache_keys=True)


def verify_token(token: str) -> dict:
    """Return the verified claims, or raise ValueError with a client-safe reason."""
    issuer, audience = os.getenv("OIDC_ISSUER", ""), os.getenv("OIDC_AUDIENCE", "")
    if not issuer or not audience:
        raise ValueError("server auth misconfigured")
    try:
        key = _jwks_client(issuer).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256", "ES256"], audience=audience, issuer=issuer,
                            options={"require": ["exp", "iat", "iss", "aud"]}, leeway=30)
    except (jwt.PyJWTError, httpx.HTTPError, KeyError) as e:
        raise ValueError("invalid token") from e
    domains = _allowed_domains()
    if domains:
        email = str(claims.get("email", "")).lower()
        if not claims.get("email_verified") or email.rsplit("@", 1)[-1] not in domains:
            raise ValueError("account not permitted")
    return claims


def _bearer(headers) -> str:
    h = headers.get("authorization", "")
    return h[7:] if h.lower().startswith("bearer ") else ""


async def require_user(request: Request) -> dict | None:
    """FastAPI dependency for REST routes."""
    if not enabled():
        return None
    try:
        return verify_token(_bearer(request.headers))
    except ValueError as e:
        raise HTTPException(401, str(e), headers={"WWW-Authenticate": "Bearer"})


def ws_user(ws: WebSocket) -> dict | None:
    """Verify a WebSocket handshake. Raises ValueError when auth is on and the token is missing/invalid."""
    if not enabled():
        return None
    return verify_token(ws.query_params.get("token") or _bearer(ws.headers))
