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
TORCH_VARIANT=cpu docker compose build backend frontend
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

The AKS deployment uses `kubernetes/overlays/aks/` over the local base. The
recommended region for the available student-subscription regions is
`southeastasia`.

The overlay adds the ACR image names, AKS application-routing ingress class,
production host settings, and Azure Key Vault Workload Identity integration.
Its placeholder values are replaced by the deployment workflow from Terraform
outputs:

```text
REPLACE_WITH_ACR_LOGIN_SERVER
REPLACE_WITH_GIT_SHA
__AKS_HOST__
__KEYVAULT_NAME__
__KEYVAULT_WORKLOAD_CLIENT_ID__
__AZURE_TENANT_ID__
```

The base images are still local-only. For AKS, render the overlay with the
ACR login server and immutable Git SHA:

```yaml
images:
  - name: enterprise-agentic-rag-backend
    newName: myregistry.azurecr.io/enterprise-agentic-rag-backend
    newTag: <git-sha>
  - name: enterprise-agentic-rag-frontend
    newName: myregistry.azurecr.io/enterprise-agentic-rag-frontend
    newTag: <git-sha>
```

The AKS cluster must enable the application routing add-on and the Azure Key
Vault Secrets Store CSI provider. The deployment workflow applies the rendered
overlay after Terraform has created the Key Vault, workload identity, and ACR.
The managed ingress class is
`webapprouting.kubernetes.azure.com`.

Azure assigns the Ingress a public IP, but no external domain is required for
this AKS validation. The simplest test path bypasses DNS entirely:

```bash
kubectl -n enterprise-rag port-forward service/rag-frontend 3000:3000
```

Open `http://localhost:3000`. If you also want to test the AKS Ingress path,
use the same `app_hostname` value in Terraform and the rendered overlay, then
map it locally after the Ingress receives an IP:

```bash
kubectl get ingress -n enterprise-rag -o wide
sudo sh -c 'echo "<EXTERNAL-IP> enterprise-agentic-rag.test" >> /etc/hosts'
```

Open `http://enterprise-agentic-rag.test`. This mapping exists only on your
laptop and does not require public DNS.

The public verification checks are the frontend root and the frontend's
backend health proxy:

```bash
curl -i -H 'Host: enterprise-agentic-rag.test' "http://<EXTERNAL-IP>/"
curl -sS -H 'Host: enterprise-agentic-rag.test' "http://<EXTERNAL-IP>/api/rag/health"
```

Use a backend service port-forward to check `/ready`; it is not a public
Ingress route:

```bash
kubectl -n enterprise-rag port-forward service/rag-backend 8000:8000
curl -i http://localhost:8000/ready
```

## Rebuild locally

```bash
docker compose build backend frontend
k3d image import enterprise-agentic-rag-backend:local enterprise-agentic-rag-frontend:local --cluster rag-local
kubectl -n enterprise-rag rollout restart deployment/rag-backend deployment/rag-frontend
```

Use `TORCH_VARIANT=cuda` instead when building for a GPU-capable target. The
variable controls image installation at build time; changing it on a running
pod cannot add or remove Torch packages.

Remove the local cluster with:

```bash
k3d cluster delete rag-local
```
