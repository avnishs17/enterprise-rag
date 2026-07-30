terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {}

  # The student subscription can expose a restricted provider catalog. Keep
  # provider registration explicit instead of blocking every plan on the
  # AzureRM registration discovery call.
  resource_provider_registrations = "none"

  storage_use_azuread = true
}
