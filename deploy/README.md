# Deploying Genome Lens

Two targets, same container image (the root `Dockerfile`; it honours `$PORT`).

## Authentication (OIDC)

Off by default. When `AUTH_ENABLED=true`, `/ws` and `/api/runs*` require a valid JWT from the configured
OIDC provider ([backend/auth.py](../backend/auth.py)):

| Variable | Meaning |
|---|---|
| `OIDC_ISSUER` | Issuer URL; keys are fetched from its `/.well-known/openid-configuration` JWKS |
| `OIDC_AUDIENCE` | Expected `aud` (e.g. your OAuth client ID) |
| `AUTH_ALLOWED_EMAIL_DOMAINS` | Optional comma list; requires a verified email in one of these domains |

Checks: RS256/ES256 signature, `iss`, `aud`, `exp`/`iat` required (30 s leeway). The WebSocket takes the token as
`?token=<jwt>` because browsers cannot set headers on a WebSocket. `/api/config` reports `auth_required`.

**Not done:** the React frontend has no login flow yet, so with auth on it cannot obtain a token. Add an OIDC
client (e.g. Google Identity Services or `oidc-client-ts`) and pass the token to the WebSocket URL. Until then,
test with a token in `curl`/`wscat`, or keep `AUTH_ENABLED=false`.

## Cloud Run

```bash
PROJECT_ID=my-proj ANTHROPIC_API_KEY=sk-ant-... ./deploy/gcp/bootstrap.sh     # once
gcloud builds submit --config deploy/gcp/cloudbuild.yaml \
  --substitutions=_OIDC_AUDIENCE=<client-id>.apps.googleusercontent.com
```

The runtime service account can read only the `anthropic-api-key` secret. `max-instances=1` and session affinity
are deliberate: the response cache, daily budget and rate limiter live in per-instance SQLite under `/tmp`.

## Kubernetes (GKE)

```bash
# edit image PROJECT_ID in kustomization.yaml, OIDC_AUDIENCE in configmap.yaml, host in ingress.yaml
kubectl apply -k deploy/k8s
kubectl -n genome-lens create secret generic genome-lens --from-literal=ANTHROPIC_API_KEY=sk-ant-...
kubectl -n genome-lens rollout status deploy/genome-lens
```

Hardening: `restricted` Pod Security, non-root, read-only root FS, all capabilities dropped, no service-account
token, NetworkPolicy limiting ingress to the app port, memory limit, readiness/liveness on `/api/health`.

Single replica with `Recreate` for the same SQLite reason; scaling out needs Redis/Postgres for the shared state.

## Status

Unit-tested: the auth module (`backend/tests/test_auth.py`). **Not executed:** the manifests, Cloud Build config and
bootstrap script have been syntax-checked only, with no GCP project or cluster available here. Expect to fix small
things on the first real deploy.
