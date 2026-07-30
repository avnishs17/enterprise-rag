# CI/CD and AKS Deployment Issues

This file records the substantive deployment issues found while moving the
project from local Docker/Kubernetes to Azure AKS. These are logical and
operational issues, not ordinary syntax or formatting errors. Each item is
paired with the fix now present in the repository.

## 1. GitHub Actions was blocked before a job started

**Symptom:** GitHub reported that the account was locked because of a billing
issue, and the workflow never entered a job.

**Cause:** This is an account or billing-state problem, not a local Git
authentication problem and not an Azure configuration problem. A correct push
can still have no runner if GitHub has disabled Actions for the account.

**Fix and prevention:** Resolve the GitHub billing restriction first, then
rerun the workflow. Confirm that the workflow has a run ID and job steps before
debugging Terraform, OIDC, or Docker.

## 2. GitHub OIDC subject did not match the federated credential

**Symptom:** Azure login failed even though the issuer and audience were
correct.

**Cause:** The repository uses GitHub's immutable OIDC subject format. The
subject includes immutable numeric owner and repository IDs as well as the
environment:

```text
repo:OWNER@OWNER_ID/REPOSITORY@REPOSITORY_ID:environment:production
```

Using the older `repo:OWNER/REPOSITORY:environment:production` form creates a
valid-looking but non-matching federated credential.

**Fix and prevention:** Terraform receives the numeric IDs and constructs the
subject for both the bootstrap and deployment identities. Retrieve them from
GitHub instead of guessing them:

```bash
export TF_VAR_github_repository_owner_id="$(gh api repos/avnishs17/enterprise-rag --jq '.owner.id')"
export TF_VAR_github_repository_id="$(gh api repos/avnishs17/enterprise-rag --jq '.id')"
```

The GitHub environment name must also exactly match Terraform's
`github_environment` value.

## 3. Terraform and deployment identities were confused

**Symptom:** The workflow either authenticated with the wrong client ID or
could not perform the operation expected by the workflow.

**Cause:** Two different GitHub identities exist by design:

- The bootstrap Terraform identity manages remote state and platform
  infrastructure.
- The platform deployment identity pushes images to ACR and accesses AKS.

They are not interchangeable. The deployment workflow must use
`AZURE_DEPLOYER_CLIENT_ID`; the Terraform workflow uses `AZURE_CLIENT_ID`.

**Fix and prevention:** Keep the two client IDs as separate GitHub environment
secrets and keep their role assignments narrow. Do not solve a wrong identity
by granting broad permissions to the deployment identity.

## 4. ACR login worked, but an unnecessary Azure read failed

**Symptom:** The deployer could log in to ACR but the workflow failed while
calling `az acr show`.

**Cause:** `AcrPush` permits registry authentication and image push, but it does
not automatically grant the Azure control-plane `Reader` permission needed to
query registry metadata. The workflow was asking Azure for information it
already had through its configured resource name.

**Fix and prevention:** The workflow derives the login server as
`<ACR_NAME>.azurecr.io` and uses the existing GitHub environment variable. It
does not add unnecessary Reader access to the deployer identity.

## 5. GitHub environment values were missing or in the wrong scope

**Symptom:** Azure login succeeded, but image tags, AKS names, Key Vault names,
or state backend values were empty.

**Cause:** GitHub Actions `secrets` and `vars` are separate namespaces, and
environment-scoped values are only available to a job that declares the same
environment. Credentials were treated as values in some places, while resource
names were treated as secrets in others.

**Fix and prevention:** Configure the `production` environment and use:

- Secrets for `AZURE_CLIENT_ID`, `AZURE_DEPLOYER_CLIENT_ID`,
  `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID`.
- Variables for `ACR_NAME`, `AKS_NAME`, `AKS_RESOURCE_GROUP`,
  `KEY_VAULT_NAME`, `KEYVAULT_WORKLOAD_CLIENT_ID`, `AKS_HOSTNAME`, and
  Terraform state names.

The workflows validate required resolved values before building or applying
manifests.

## 6. The local `.env` was not automatically available in AKS

**Symptom:** The application container started without the complete local
runtime configuration, or only a hand-picked subset of API keys was present.

**Cause:** GitHub Actions does not upload the developer's local `.env`, and
Terraform should not put application secrets in Terraform state. The UI also
has deployment topology values that should not be treated as secrets.

**Fix and prevention:** `scripts/seed-key-vault.sh .env` migrates every
environment entry to Key Vault, including the values consumed by
`app/config.py`. AKS syncs those secrets through the Secrets Store CSI Driver.
`RAG_API_URL` remains deployment topology: local UI configuration points to
localhost, while the AKS frontend points to `http://rag-backend:8000`.

## 7. A single AKS node could not perform a rolling backend update

**Symptom:** The new backend pod stayed `Pending` with `Insufficient cpu`,
while the old backend pod remained healthy. The deployment workflow waited for
the rollout and could not complete.

**Cause:** The `Standard_B2s_v2` test cluster has limited allocatable CPU. A
normal rolling update temporarily requires the old and new backend pods at the
same time, even though the steady-state deployment needs only one backend
pod.

**Fix and prevention:** The AKS overlay uses `strategy: Recreate`, allowing the
old backend pod to stop before the new one is scheduled. This fits the
disposable one-node test cluster but causes a short backend interruption. A
production cluster should use multiple appropriately sized nodes and return
to a rolling strategy.

## 8. The HTTP `.test` hostname broke a browser-only code path

**Symptom:** Ingress returned the Next.js page successfully, but the browser
showed a client-side exception immediately after loading it.

**Cause:** `enterprise-agentic-rag.test` is intentionally mapped to the AKS IP
and served over HTTP. Browsers do not expose every secure-context Web Crypto
API on an ordinary HTTP origin, including `crypto.randomUUID()`.

**Fix and prevention:** The frontend now uses `crypto.randomUUID()` when
available and a local fallback for the HTTP validation origin. A production
deployment should use HTTPS with a real certificate and domain. After an image
rollout, hard-refresh the browser to discard an older Next.js bundle.

## 9. Interrupting Terraform can leave a state lock

**Symptom:** A second `terraform plan` reported that the state lock was held by
an `OperationTypeApply` process after the original terminal had been stopped.

**Cause:** Terraform locks state during writes to prevent concurrent changes.
The lock may remain briefly while a process exits or may be stale after an
interrupted apply.

**Fix and prevention:** First confirm that no Terraform apply is still running
and wait for Azure operations to settle. Only then use the exact lock ID with
`terraform force-unlock` if the lock is stale. Do not use `-lock=false` for
apply or destroy; it can corrupt shared state.

## 10. The Ingress IP is host-routed, not a backend public port

**Symptom:** Calling the assigned IP without a hostname returned `404`, and
calling `http://<IP>:8000` timed out.

**Cause:** The AKS application-routing Ingress listens publicly on port `80`
and selects a rule using the HTTP `Host` header. The backend service listens on
port `8000` as a Kubernetes `ClusterIP`; it is intentionally not exposed to
the Internet.

**Fix and prevention:** Map the test hostname locally and use the hostname, or
send the equivalent Host header:

```bash
sudo sh -c 'printf "%s enterprise-agentic-rag.test\\n" "<EXTERNAL-IP>" >> /etc/hosts'
curl -H 'Host: enterprise-agentic-rag.test' http://<EXTERNAL-IP>/
```

Use `kubectl port-forward service/rag-backend 8000:8000` only for an internal
backend check.

## 11. Azure provider registration was a subscription prerequisite

**Symptom:** Terraform could be valid locally but resource creation failed
because an Azure resource provider was not registered in the student
subscription.

**Cause:** This subscription uses a restricted provider catalog, and the
Terraform AzureRM configuration disables its automatic provider-registration
scan. Provider registration is an Azure subscription operation, not an
application resource that should be recreated on every platform apply.

**Fix and prevention:** Register the required namespaces once with Azure CLI
before bootstrap. The exact command is documented in `docs/terraform.md`.
The registration command does not create an AKS, ACR, Key Vault, or application
resource; it only enables the subscription providers Terraform will use.

## Current validation result

The final validated path is:

```text
GitHub push -> CI -> ACR CPU image builds -> AKS manifest render/apply
-> backend/frontend rollout -> Ingress HTTP 200 -> /api/rag/health = {"status":"ok"}
```

The deployment remains a disposable test environment. Authentication,
authorization, tenant isolation, durable upload workers, HTTPS, autoscaling,
monitoring, and backup/restore still require production hardening.
