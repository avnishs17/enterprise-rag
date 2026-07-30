# GitHub Actions Deployment

The repository uses GitHub OIDC, so no Azure client secret is stored in
GitHub. Create the GitHub environment `production` before running either
workflow. Its name must match the federated identity created by Terraform.

Run the commands below from the repository root after the bootstrap and
platform Terraform applies. They use the current Terraform outputs, so no
client IDs or resource names need to be copied manually. Install and
authenticate the GitHub CLI first with `gh auth login`. If you opened a new
terminal, initialize the platform backend metadata first:

```bash
export TF_DATA_DIR="$PWD/.terraform-data/platform"
```

Create the environment:

```bash
gh api --method PUT \
  "repos/$(gh repo view --json nameWithOwner --jq .nameWithOwner)/environments/production"
```

## Required secrets

Set these repository or `production` environment secrets:

- `AZURE_CLIENT_ID`: the bootstrap output `github_terraform_client_id`
- `AZURE_DEPLOYER_CLIENT_ID`: the platform output `github_deployer_client_id`
- `AZURE_TENANT_ID`: the Azure tenant ID
- `AZURE_SUBSCRIPTION_ID`: the Azure subscription ID

The two client IDs are different. Terraform uses the bootstrap identity to
manage the platform and its remote state. The deploy workflow uses the
least-privilege platform identity to push images and access AKS.

Set them with the GitHub CLI:

```bash
gh secret set AZURE_CLIENT_ID --env production \
  --body "$(terraform -chdir=infra/terraform/bootstrap output -raw github_terraform_client_id)"
gh secret set AZURE_DEPLOYER_CLIENT_ID --env production \
  --body "$(terraform -chdir=infra/terraform/platform output -raw github_deployer_client_id)"
gh secret set AZURE_TENANT_ID --env production \
  --body "$(az account show --query tenantId -o tsv)"
gh secret set AZURE_SUBSCRIPTION_ID --env production \
  --body "$(az account show --query id -o tsv)"
```

## Required variables

Set these repository or `production` environment variables:

```text
TF_STATE_RESOURCE_GROUP=rg-enterprise-rag-tfstate
TF_STATE_STORAGE_ACCOUNT=<bootstrap state storage account>
TF_STATE_CONTAINER=tfstate
TF_STATE_KEY=platform.tfstate
AKS_HOSTNAME=enterprise-agentic-rag.test
ACR_NAME=<platform ACR name>
AKS_NAME=aks-enterprise-rag
AKS_RESOURCE_GROUP=rg-enterprise-rag
KEY_VAULT_NAME=<platform Key Vault name>
KEYVAULT_WORKLOAD_CLIENT_ID=<platform Workload Identity client ID>
```

Set the variables from Terraform outputs:

```bash
gh variable set TF_STATE_RESOURCE_GROUP --env production \
  --body "$(terraform -chdir=infra/terraform/bootstrap output -raw state_resource_group_name)"
gh variable set TF_STATE_STORAGE_ACCOUNT --env production \
  --body "$(terraform -chdir=infra/terraform/bootstrap output -raw state_storage_account_name)"
gh variable set TF_STATE_CONTAINER --env production \
  --body "$(terraform -chdir=infra/terraform/bootstrap output -raw state_container_name)"
gh variable set TF_STATE_KEY --env production --body "platform.tfstate"
gh variable set AKS_HOSTNAME --env production \
  --body "$(terraform -chdir=infra/terraform/platform output -raw app_hostname)"
gh variable set ACR_NAME --env production \
  --body "$(terraform -chdir=infra/terraform/platform output -raw acr_name)"
gh variable set AKS_NAME --env production \
  --body "$(terraform -chdir=infra/terraform/platform output -raw aks_name)"
gh variable set AKS_RESOURCE_GROUP --env production \
  --body "$(terraform -chdir=infra/terraform/platform output -raw aks_resource_group_name)"
gh variable set KEY_VAULT_NAME --env production \
  --body "$(terraform -chdir=infra/terraform/platform output -raw key_vault_name)"
gh variable set KEYVAULT_WORKLOAD_CLIENT_ID --env production \
  --body "$(terraform -chdir=infra/terraform/platform output -raw keyvault_workload_client_id)"
```

Verify names without printing secret values:

```bash
gh secret list --env production
gh variable list --env production
```

Get the values created by the current local apply with:

```bash
terraform -chdir=infra/terraform/bootstrap output
terraform -chdir=infra/terraform/platform output
```

The root `.env` is not uploaded by GitHub Actions. It has already been
migrated to Key Vault with `scripts/seed-key-vault.sh`; AKS reads those values
through the Secrets Store CSI Driver and Workload Identity.

## End-to-end run

1. Complete local validation in [local setup](local-setup.md), [Docker](docker.md), and [Kubernetes](kubernetes.md).
2. Log in to Azure, register the required providers, and apply the bootstrap and platform stacks using [Terraform](terraform.md).
3. Run `scripts/seed-key-vault.sh .env` and verify the Key Vault secret count.
4. Configure the `production` GitHub environment and run the secret/variable commands above.
5. Review and push the changes:

   ```bash
   git diff --check
   git add -A
   git diff --cached --stat
   git commit -m "Add Azure AKS deployment automation"
   git push origin main
   ```

6. Confirm `CI` passes. `Terraform Platform` runs a plan on infrastructure changes; use its manual `apply` input only after reviewing that plan. `Deploy AKS` builds, pushes, and rolls out both images.

The first push must happen only after the GitHub environment values exist;
otherwise the workflows will fail at Azure login or when resolving resource
names.

## Workflows

- `CI` runs backend tests/lint, frontend tests/build, and Kustomize rendering.
- `Terraform Platform` plans on `main` changes. Run it manually with `apply`
  checked to apply the reviewed plan.
- `Deploy AKS` builds CPU-based backend and frontend images, pushes both to
  ACR, and rolls out the commit SHA to AKS. It can also be started manually.

The bootstrap stack is intentionally not in GitHub Actions. It creates the
remote state and the identity needed by Actions, so it remains a one-time
local operation. Do not destroy bootstrap resources while the platform
workflow still needs its state or OIDC identity.

The hostname is a local test name, not a purchased domain. After deployment,
use port-forwarding or map the AKS ingress IP to `enterprise-agentic-rag.test`
in `/etc/hosts`; external DNS is not required for this validation.

## Verify AKS manually

The deployment workflow configures its own runner context. To inspect the
cluster locally after deployment:

```bash
az aks install-cli
az aks get-credentials \
  --resource-group "$(terraform -chdir=infra/terraform/platform output -raw aks_resource_group_name)" \
  --name "$(terraform -chdir=infra/terraform/platform output -raw aks_name)" \
  --overwrite-existing
kubelogin convert-kubeconfig -l azurecli
kubectl -n enterprise-rag get pods,services,ingress
kubectl -n enterprise-rag rollout status deployment/rag-backend
kubectl -n enterprise-rag rollout status deployment/rag-frontend
```

For a frontend-only check, port-forward the frontend service and open
<http://localhost:3000>:

```bash
kubectl -n enterprise-rag port-forward service/rag-frontend 3000:3000
```

For the public Ingress test used by the validated deployment, get the assigned
IP and map the configured test hostname locally:

```bash
INGRESS_IP="$(kubectl -n enterprise-rag get ingress rag-frontend -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"
printf '%s enterprise-agentic-rag.test\n' "$INGRESS_IP"
sudo sh -c "printf '%s enterprise-agentic-rag.test\\n' '$INGRESS_IP' >> /etc/hosts"

curl -i -H 'Host: enterprise-agentic-rag.test' "http://${INGRESS_IP}/"
curl -sS -H 'Host: enterprise-agentic-rag.test' "http://${INGRESS_IP}/api/rag/health"
```

The expected public responses are HTTP `200` for `/` and
`{"status":"ok"}` for `/api/rag/health`. The backend `/ready` endpoint is an
internal Kubernetes probe and is not routed through the frontend proxy. Check
it directly when needed:

```bash
kubectl -n enterprise-rag port-forward service/rag-backend 8000:8000
curl -i http://localhost:8000/ready
```

The `.test` hostname is served over HTTP for this disposable validation. A
browser may retain an older Next.js bundle after an image rollout; use a hard
refresh (`Ctrl+Shift+R`) when validating a newly deployed frontend.

See [ci-cd-issues.md](ci-cd-issues.md) for the logical deployment failures
encountered during this setup and the preventive checks now captured in the
repository.

## Tear down the test deployment

Destroy the platform before destroying bootstrap. The platform needs the
bootstrap-created remote state storage while it is being destroyed:

```bash
export TF_DATA_DIR="$PWD/.terraform-data/platform"
terraform -chdir=infra/terraform/platform plan -destroy
terraform -chdir=infra/terraform/platform destroy

terraform -chdir=infra/terraform/bootstrap plan -destroy
terraform -chdir=infra/terraform/bootstrap destroy
```

This removes the Terraform-managed Azure resource groups, AKS, ACR, Key Vault,
managed identities, role assignments, and remote state storage. It does not
remove GitHub environment secrets/variables; delete those separately from the
repository settings if they are no longer needed.
