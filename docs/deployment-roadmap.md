# Deployment roadmap

This project is ready to move from local Docker validation into Kubernetes and CI/CD. Keep cloud-specific guides separate from the root README.

## Recommended order

```text
1. Local Docker validation
2. Local Kubernetes manifests
3. CI: lint, tests, builds
4. Registry push
5. CD to cloud Kubernetes
6. Production hardening
```

## Local Kubernetes next

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

## CI/CD guides to add later

Use separate docs when implementing provider-specific deployment:

```text
docs/kubernetes.md
docs/cicd-github-actions.md
docs/aws-eks.md
docs/azure-aks.md
```

## Production blockers before real users

- Replace in-memory upload jobs with a durable worker queue.
- Add real user authentication, authorization, and tenant isolation.
- Add monitoring alerts and dashboards.
- Add backup/restore policy for Qdrant, Redis history, and Neon.
- Add Locust load tests for `/query` and `/query/stream`.
- Decide cloud registry and secret manager:
  - AWS: ECR + Secrets Manager/Parameter Store + EKS
  - Azure: ACR + Key Vault + AKS
