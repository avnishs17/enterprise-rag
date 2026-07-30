# Terraform Azure Deployment

Terraform is split into two stacks:

- `infra/terraform/bootstrap`: creates the project resource group, remote state
  storage, and the GitHub Actions Terraform identity.
- `infra/terraform/platform`: creates ACR, AKS, Key Vault, Workload Identity,
  federated credentials, and deployment permissions.

The default region is `southeastasia`, which is available in the student
subscription used for this project.

## Prerequisites

Install Azure CLI and Terraform, then authenticate locally:

```bash
az login
az account set --subscription "<student-subscription-id>"
```

Confirm that the selected subscription is the intended student subscription:

```bash
az account show --query '{name:name,subscriptionId:id,tenantId:tenantId}' -o table
```

This configuration disables AzureRM's automatic provider-registration scan
because the student subscription exposes a restricted provider catalog. Ensure
the resource providers used by this stack are registered before the first
Terraform apply:

```bash
for provider in \
  Microsoft.Resources Microsoft.Storage Microsoft.ManagedIdentity \
  Microsoft.Authorization Microsoft.ContainerRegistry Microsoft.ContainerService \
  Microsoft.KeyVault Microsoft.Network; do
  az provider register --namespace "$provider" --wait
done
```

The Azure user running the bootstrap must be able to create role assignments.
`Contributor` alone is insufficient; `Owner`, `User Access Administrator`, or
`Role Based Access Control Administrator` is required at the relevant scope.

## Bootstrap

Set the required Terraform variables in the shell. They are not stored in the
repository, and no `terraform.tfvars` file is required:

```bash
export TF_VAR_github_repository="avnishs17/enterprise-rag"
export TF_VAR_github_environment="production"
export TF_VAR_github_repository_owner_id="$(gh api repos/avnishs17/enterprise-rag --jq '.owner.id')"
export TF_VAR_github_repository_id="$(gh api repos/avnishs17/enterprise-rag --jq '.id')"
```

Change `TF_VAR_github_repository` and the `gh api` repository path if deploying
a fork. The numeric IDs are required because newer GitHub repositories use
immutable OIDC subjects.

Then run:

```bash
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap validate
terraform -chdir=infra/terraform/bootstrap plan
terraform -chdir=infra/terraform/bootstrap apply
```

The bootstrap output `github_terraform_client_id` becomes the GitHub Actions
`AZURE_CLIENT_ID`. No client secret is created; GitHub authenticates with OIDC.

## Platform

Set the platform hostname. The repository and environment variables exported
above are reused by this stack:

```bash
export TF_VAR_app_hostname="enterprise-agentic-rag.test"
```

`app_hostname` must contain a hostname only, without `https://`. Terraform
does not verify domain ownership or DNS. The example uses the reserved local
test name `enterprise-agentic-rag.test`; no external domain or public DNS is
needed for this AKS validation.

Initialize the platform backend from the bootstrap outputs:

```bash
bash scripts/terraform-platform-init.sh
```

The helper reads the resource group, storage account, and container names from
the applied bootstrap state. No backend placeholder needs to be edited.

The helper stores platform Terraform metadata under `.terraform-data/platform`
so it does not depend on provider files created by another user or container:

```bash
export TF_DATA_DIR="$PWD/.terraform-data/platform"
```

Review and apply the platform:

```bash
export TF_DATA_DIR="$PWD/.terraform-data/platform"
terraform -chdir=infra/terraform/platform validate
terraform -chdir=infra/terraform/platform plan
terraform -chdir=infra/terraform/platform apply
```

The default AKS node size is `Standard_B2s_v2`, selected for the student
subscription's Southeast Asia quota. Override `node_vm_size` only after
checking that the target VM family is both available and within quota.

The platform outputs provide the ACR login server, AKS name, Key Vault name,
and Workload Identity client IDs needed by the Kubernetes deployment workflow.

## Secret population

Terraform creates the Key Vault and access policies but does not store
application values in Terraform state. The migration helper reads every
`KEY=value` entry in the root `.env` and uploads it using the Key Vault naming
convention `KEY_NAME` -> `key-name`. This keeps the complete runtime
configuration, including values consumed by `app/config.py`, available to the
AKS deployment instead of silently dropping less common integrations.

`QDRANT_CLUSTER_ENDPOINT` is the legacy local name. It is uploaded as
`qdrant-url` and exposed to the application as `QDRANT_URL`, which is the
canonical setting accepted by the backend configuration.

For the fast one-time migration from the normalized local `.env`, use:

```bash
export KEY_VAULT_NAME="$(terraform -chdir=infra/terraform/platform output -raw key_vault_name)"
bash scripts/seed-key-vault.sh .env
az keyvault secret list --vault-name "$KEY_VAULT_NAME" --query 'length(@)' -o tsv
```

The final command should equal the number of environment variables migrated
(currently `41`). The script reads values locally, sends them directly to Key
Vault, and prints only the names of successfully seeded secrets. It is a
migration helper, not a runtime environment loader.

## UI environment

`ui/.env` is local-only and is not copied into Key Vault. The UI example file
contains `RAG_API_URL` and `RAG_API_KEY`:

- Locally, `RAG_API_URL` points to `127.0.0.1:8000`.
- In AKS, the frontend uses the internal Kubernetes service URL
  `http://rag-backend:8000`.
- `RAG_API_KEY` is part of the root `.env` migration and is injected into the
  frontend from the synced Key Vault secret.

Do not migrate a local `RAG_API_URL` value into Key Vault; it is deployment
topology, not a secret.

## Destroy the disposable test environment

Destroy the platform stack first, then the bootstrap stack. The platform uses
the bootstrap-created storage account for its remote state:

```bash
export TF_DATA_DIR="$PWD/.terraform-data/platform"
terraform -chdir=infra/terraform/platform plan -destroy
terraform -chdir=infra/terraform/platform destroy

terraform -chdir=infra/terraform/bootstrap plan -destroy
terraform -chdir=infra/terraform/bootstrap destroy
```

Review each destroy plan carefully. This removes the Terraform-managed Azure
resource groups, AKS, ACR, Key Vault, identities, role assignments, and state
storage. It does not delete GitHub environment secrets or variables.

## Clean up Azure-created Network Watcher

Azure may create `NetworkWatcherRG` outside Terraform when network features are
enabled. Terraform destroy does not remove it. Inspect the group first:

```bash
NETWORK_WATCHER_RG="${NETWORK_WATCHER_RG:-NetworkWatcherRG}"
az resource list --resource-group "$NETWORK_WATCHER_RG" \
  --query '[].{name:name,type:type,location:location}' -o table
```

Only run the deletion when this is a disposable subscription and the group
contains no resources needed by another deployment:

```bash
az group delete --name "$NETWORK_WATCHER_RG" --yes --no-wait
az group wait --deleted --name "$NETWORK_WATCHER_RG" --interval 15 --timeout 600
```

This is a subscription-level cleanup step, not a Terraform resource. Deleting
a shared Network Watcher can affect diagnostics for unrelated Azure workloads.
