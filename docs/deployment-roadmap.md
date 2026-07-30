# Deployment roadmap

This project has completed local Docker/Kubernetes validation and has an Azure
AKS deployment path. Keep cloud-specific commands in the dedicated guides.

## Recommended order

```text
1. Local Docker validation: [Docker guide](docker.md)
2. Local Kubernetes validation: [Kubernetes guide](kubernetes.md)
3. Azure bootstrap and platform: [Terraform guide](terraform.md)
4. Key Vault migration and GitHub OIDC setup: [GitHub Actions guide](github-actions.md)
5. CI, ACR image push, and AKS rollout through GitHub Actions
6. Production hardening
```

## Runtime layout

Create Kubernetes manifests for two runtime workloads:

```text
rag-backend Deployment + Service
rag-frontend Deployment + Service + Ingress
```

Expected internal service link:

```text
frontend Next.js proxy -> http://rag-backend:8000
```

Backend needs secrets/config for external services:

- Jina
- Nebius
- Groq
- Qdrant
- Neon
- Upstash Redis
- Mem0
- RAG API key
- Logfire/LangSmith if enabled

Frontend needs only server-side proxy config:

- `RAG_API_URL=http://rag-backend:8000`
- `RAG_API_KEY=<same backend bearer key>`

## Terraform and CI/CD

Azure infrastructure is defined under `infra/terraform/`. Use the bootstrap
stack once to create remote state and the GitHub OIDC Terraform identity, then
use the platform stack for AKS, ACR, Key Vault, and Workload Identity. See
`docs/terraform.md`. The complete GitHub Actions sequence, including Key Vault
secret migration and environment configuration, is in
`docs/github-actions.md`.

## Production blockers before real users

- Replace in-memory upload jobs with a durable worker queue.
- Add real user authentication, authorization, and tenant isolation.
- Add monitoring alerts and dashboards.
- Add backup/restore policy for Qdrant, Redis history, and Neon.
- Add Locust load tests for `/query` and `/query/stream`.
- Decide whether to retain the current Azure deployment or create a separate
  AWS implementation; the current tested path is Azure ACR + Key Vault + AKS.
