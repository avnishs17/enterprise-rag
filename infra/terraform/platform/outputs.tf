output "acr_name" {
  value = azurerm_container_registry.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "aks_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "aks_resource_group_name" {
  value = data.azurerm_resource_group.project.name
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "keyvault_workload_client_id" {
  value = azurerm_user_assigned_identity.keyvault_workload.client_id
}

output "github_deployer_client_id" {
  value = azurerm_user_assigned_identity.github_deployer.client_id
}

output "tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "subscription_id" {
  value = data.azurerm_client_config.current.subscription_id
}

output "app_hostname" {
  value = var.app_hostname
}
