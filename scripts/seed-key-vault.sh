#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env}"
KEY_VAULT_NAME="${KEY_VAULT_NAME:?Set KEY_VAULT_NAME to the Terraform Key Vault output}"

if [[ ! -f "$ENV_FILE" ]]; then
  printf 'Environment file not found: %s\n' "$ENV_FILE" >&2
  exit 1
fi

get_value() {
  local key="$1"
  awk -v key="$key" '
    index($0, key "=") == 1 {
      sub("^[^=]*=", "")
      print
      exit
    }
  ' "$ENV_FILE"
}

seed_secret() {
  local env_name="$1"
  local vault_name="$2"
  shift 2
  local value
  local source_name

  value=""
  for source_name in "$env_name" "$@"; do
    value="$(get_value "$source_name")"
    if [[ -n "$value" ]]; then
      break
    fi
  done

  if [[ -z "$value" ]]; then
    printf 'Missing or empty required value: %s\n' "$env_name" >&2
    exit 1
  fi

  az keyvault secret set \
    --vault-name "$KEY_VAULT_NAME" \
    --name "$vault_name" \
    --value "$value" \
    --only-show-errors \
    --output none

  printf 'Seeded %s\n' "$vault_name"
}

# Key Vault secret names use hyphens; the aliases are mapped back to the
# application's environment variable names by the AKS SecretProviderClass.
# Preserve every value in the normalized root .env. Key Vault names are derived
# from the environment names, except the legacy QDRANT alias which is exposed
# to the application as QDRANT_URL.
while IFS= read -r env_name; do
  if [[ "$env_name" == "QDRANT_CLUSTER_ENDPOINT" ]]; then
    continue
  fi

  vault_name="${env_name,,}"
  vault_name="${vault_name//_/-}"
  seed_secret "$env_name" "$vault_name"
done < <(awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{print $1}' "$ENV_FILE" | sort -u)

if [[ -z "$(get_value QDRANT_URL)" ]]; then
  seed_secret QDRANT_URL qdrant-url QDRANT_CLUSTER_ENDPOINT
fi
