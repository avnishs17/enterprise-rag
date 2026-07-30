data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "project" {
  name = var.project_resource_group_name
}

resource "random_string" "suffix" {
  length  = 6
  lower   = true
  numeric = true
  special = false
  upper   = false
}

locals {
  acr_name       = var.acr_name != "" ? var.acr_name : "acr${replace(var.project_slug, "-", "")}${random_string.suffix.result}"
  key_vault_name = var.key_vault_name != "" ? var.key_vault_name : "kv-${var.project_slug}-${random_string.suffix.result}"
}

resource "azurerm_container_registry" "main" {
  name                = local.acr_name
  resource_group_name = data.azurerm_resource_group.project.name
  location            = data.azurerm_resource_group.project.location
  sku                 = "Basic"
  admin_enabled       = false
}

resource "azurerm_kubernetes_cluster" "main" {
  name                = var.cluster_name
  location            = data.azurerm_resource_group.project.location
  resource_group_name = data.azurerm_resource_group.project.name
  dns_prefix          = var.cluster_name
  sku_tier            = "Free"

  default_node_pool {
    name                         = "system"
    vm_size                      = var.node_vm_size
    node_count                   = var.node_count
    type                         = "VirtualMachineScaleSets"
    only_critical_addons_enabled = false

    upgrade_settings {
      max_surge = "10%"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  role_based_access_control_enabled = true
  local_account_disabled            = true
  oidc_issuer_enabled               = true
  workload_identity_enabled         = true

  azure_active_directory_role_based_access_control {
    azure_rbac_enabled = true
    tenant_id          = data.azurerm_client_config.current.tenant_id
  }

  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "2m"
  }

  web_app_routing {
    dns_zone_ids             = []
    default_nginx_controller = "External"
  }
}

resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
}

resource "azurerm_key_vault" "main" {
  name                          = local.key_vault_name
  location                      = data.azurerm_resource_group.project.location
  resource_group_name           = data.azurerm_resource_group.project.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = false
  soft_delete_retention_days    = 7
  public_network_access_enabled = true
}

resource "azurerm_user_assigned_identity" "keyvault_workload" {
  name                = "id-${var.project_slug}-keyvault"
  location            = data.azurerm_resource_group.project.location
  resource_group_name = data.azurerm_resource_group.project.name
}

resource "azurerm_role_assignment" "keyvault_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.keyvault_workload.principal_id
}

resource "azurerm_role_assignment" "current_keyvault_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_federated_identity_credential" "keyvault_workload" {
  name                      = "aks-enterprise-rag-backend"
  user_assigned_identity_id = azurerm_user_assigned_identity.keyvault_workload.id
  issuer                    = azurerm_kubernetes_cluster.main.oidc_issuer_url
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "system:serviceaccount:enterprise-rag:rag-backend"
}

resource "azurerm_user_assigned_identity" "github_deployer" {
  name                = "id-${var.project_slug}-deployer"
  location            = data.azurerm_resource_group.project.location
  resource_group_name = data.azurerm_resource_group.project.name
}

resource "azurerm_federated_identity_credential" "github_deployer" {
  name                      = "github-${var.github_environment}"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_deployer.id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:${var.github_repository}:environment:${var.github_environment}"
}

resource "azurerm_role_assignment" "github_acr_push" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.github_deployer.principal_id
}

resource "azurerm_role_assignment" "github_aks_cluster_user" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = azurerm_user_assigned_identity.github_deployer.principal_id
}

resource "azurerm_role_assignment" "github_aks_rbac_admin" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = azurerm_user_assigned_identity.github_deployer.principal_id
}

resource "azurerm_role_assignment" "current_aks_cluster_user" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "current_aks_rbac_admin" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = data.azurerm_client_config.current.object_id
}
