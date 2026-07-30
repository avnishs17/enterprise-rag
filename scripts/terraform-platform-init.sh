#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_BIN="${TERRAFORM_BIN:-terraform}"
BOOTSTRAP_DIR="$REPO_ROOT/infra/terraform/bootstrap"
PLATFORM_DIR="$REPO_ROOT/infra/terraform/platform"
TF_DATA_DIR="${TF_DATA_DIR:-$REPO_ROOT/.terraform-data/platform}"

if [[ ! -d "$BOOTSTRAP_DIR/.terraform" ]]; then
  printf 'Bootstrap Terraform state is not initialized: %s\n' "$BOOTSTRAP_DIR" >&2
  printf 'Run terraform -chdir=infra/terraform/bootstrap init first.\n' >&2
  exit 1
fi

mkdir -p "$TF_DATA_DIR"

state_resource_group_name="$($TERRAFORM_BIN -chdir="$BOOTSTRAP_DIR" output -raw state_resource_group_name)"
state_storage_account_name="$($TERRAFORM_BIN -chdir="$BOOTSTRAP_DIR" output -raw state_storage_account_name)"
state_container_name="$($TERRAFORM_BIN -chdir="$BOOTSTRAP_DIR" output -raw state_container_name)"

if [[ -z "$state_resource_group_name" || -z "$state_storage_account_name" || -z "$state_container_name" ]]; then
  printf 'Bootstrap outputs are incomplete; apply the bootstrap stack first.\n' >&2
  exit 1
fi

exec env TF_DATA_DIR="$TF_DATA_DIR" "$TERRAFORM_BIN" -chdir="$PLATFORM_DIR" init \
  -backend-config="resource_group_name=$state_resource_group_name" \
  -backend-config="storage_account_name=$state_storage_account_name" \
  -backend-config="container_name=$state_container_name" \
  -backend-config="key=platform.tfstate"
