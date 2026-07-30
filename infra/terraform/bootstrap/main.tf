data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  lower   = true
  numeric = true
  special = false
  upper   = false
}

locals {
  state_storage_account_name = var.state_storage_account_name != "" ? var.state_storage_account_name : "st${replace(var.project_slug, "-", "")}${random_string.suffix.result}"
  github_identity_name       = "id-${var.project_slug}-terraform"
  github_repository_owner    = split("/", var.github_repository)[0]
  github_repository_name     = split("/", var.github_repository)[1]
  github_oidc_subject        = "repo:${local.github_repository_owner}@${var.github_repository_owner_id}/${local.github_repository_name}@${var.github_repository_id}:environment:${var.github_environment}"
}

resource "azurerm_resource_group" "state" {
  name     = var.state_resource_group_name
  location = var.location
}

resource "azurerm_resource_group" "project" {
  name     = var.project_resource_group_name
  location = var.location
}

resource "azurerm_storage_account" "state" {
  name                            = local.state_storage_account_name
  resource_group_name             = azurerm_resource_group.state.name
  location                        = azurerm_resource_group.state.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = true
  shared_access_key_enabled       = false
}

resource "azurerm_storage_container" "state" {
  name                  = var.state_container_name
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"

  depends_on = [azurerm_role_assignment.current_state_blob]
}

resource "azurerm_user_assigned_identity" "github_terraform" {
  name                = local.github_identity_name
  resource_group_name = azurerm_resource_group.state.name
  location            = azurerm_resource_group.state.location
}

resource "azurerm_federated_identity_credential" "github_production" {
  name                      = "github-production"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_terraform.id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = local.github_oidc_subject
}

resource "azurerm_role_assignment" "current_state_blob" {
  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "github_state_blob" {
  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.github_terraform.principal_id
}

resource "azurerm_role_assignment" "github_platform_contributor" {
  scope                = azurerm_resource_group.project.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.github_terraform.principal_id
}

resource "azurerm_role_assignment" "github_platform_rbac_admin" {
  scope                = azurerm_resource_group.project.id
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azurerm_user_assigned_identity.github_terraform.principal_id
}
