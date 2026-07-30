output "state_resource_group_name" {
  value = azurerm_resource_group.state.name
}

output "state_storage_account_name" {
  value = azurerm_storage_account.state.name
}

output "state_container_name" {
  value = azurerm_storage_container.state.name
}

output "project_resource_group_name" {
  value = azurerm_resource_group.project.name
}

output "github_terraform_client_id" {
  value = azurerm_user_assigned_identity.github_terraform.client_id
}

output "github_terraform_principal_id" {
  value = azurerm_user_assigned_identity.github_terraform.principal_id
}

output "tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "subscription_id" {
  value = data.azurerm_client_config.current.subscription_id
}
