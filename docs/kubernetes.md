# Kubernetes Deployment

The manifests in `kubernetes/` are provider-neutral Kubernetes resources. They
run the stateless backend and frontend while Qdrant, Neon, Upstash Redis, Mem0,
Jina, Nebius, and Groq remain external managed services.

## Local k3d

Prerequisites: Docker, `k3d`, `kubectl`, and a root `.env` with the required
service credentials.

Stop Compose if it is running, but keep Docker running:

```bash
docker compose down
k3d cluster create rag-local --servers 1 --agents 0 --wait -p "8080:80@loadbalancer"
```

Build and import the local images:

```bash
docker compose build backend frontend
k3d image import enterprise-agentic-rag-backend:local enterprise-agentic-rag-frontend:local --cluster rag-local
```

Create the Kubernetes Secret from `.env`; credentials are not stored in YAML.
Remove any obsolete legacy keys from `.env` first, including `OPENAI_API_KEY`:

```bash
kubectl create namespace enterprise-rag --dry-run=client -o yaml | kubectl apply -f -
kubectl -n enterprise-rag create secret generic rag-backend-secrets \
  --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
```

Apply and inspect:

```bash
kubectl apply -k kubernetes/
kubectl -n enterprise-rag get pods,services,ingress
kubectl -n enterprise-rag rollout status deployment/rag-backend
kubectl -n enterprise-rag rollout status deployment/rag-frontend
```

Open <http://rag.localhost:8080>. Alternatively, bypass Ingress:

```bash
kubectl -n enterprise-rag port-forward service/rag-frontend 3000:3000
```

The backend readiness probe checks configured external dependencies. A `503`
from `/ready` means one of those services or credentials is unavailable.

## Azure AKS changes

The same `kubernetes/` resources can be used in AKS. Update the `images` block
in `kubernetes/kustomization.yaml` to point at ACR, for example:

```yaml
images:
  - name: enterprise-agentic-rag-backend
    newName: myregistry.azurecr.io/enterprise-agentic-rag-backend
    newTag: <git-sha>
  - name: enterprise-agentic-rag-frontend
    newName: myregistry.azurecr.io/enterprise-agentic-rag-frontend
    newTag: <git-sha>
```

Then replace the local Secret creation with an AKS-compatible secret manager
workflow, such as Azure Key Vault CSI or a CI/CD-injected Kubernetes Secret.
Set the Ingress host and `RAG_API_URL`/trusted-host values for the AKS domain,
and add the Ingress class or controller annotations required by the chosen AKS
Ingress controller.

## Rebuild locally

```bash
docker compose build backend frontend
k3d image import enterprise-agentic-rag-backend:local enterprise-agentic-rag-frontend:local --cluster rag-local
kubectl -n enterprise-rag rollout restart deployment/rag-backend deployment/rag-frontend
```

Remove the local cluster with:

```bash
k3d cluster delete rag-local
```
