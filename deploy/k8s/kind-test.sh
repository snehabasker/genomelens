#!/usr/bin/env bash
# Local smoke test on a throwaway kind cluster. Needs docker, kind, kubectl.
# Skips ingress.yaml (GKE-only ManagedCertificate) and runs with auth off.
set -euo pipefail
cd "$(dirname "$0")/../.."

kind get clusters | grep -qx genome-lens || kind create cluster --name genome-lens
docker build -t genome-lens:local .
kind load docker-image genome-lens:local --name genome-lens

kubectl apply -f deploy/k8s/namespace.yaml
kubectl -n genome-lens apply -f deploy/k8s/configmap.yaml -f deploy/k8s/service.yaml -f deploy/k8s/networkpolicy.yaml
kubectl -n genome-lens patch configmap genome-lens --type merge -p '{"data":{"AUTH_ENABLED":"false"}}'
sed 's#image: genome-lens#image: genome-lens:local\n          imagePullPolicy: Never#' deploy/k8s/deployment.yaml |
  kubectl -n genome-lens apply -f -

kubectl -n genome-lens rollout status deploy/genome-lens --timeout=180s
kubectl -n genome-lens port-forward svc/genome-lens 8080:80 &
PF=$!; trap 'kill $PF' EXIT; sleep 3
curl -fsS localhost:8080/api/health && echo && echo "OK: deployed and healthy"
