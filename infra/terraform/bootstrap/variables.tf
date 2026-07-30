variable "location" {
  type        = string
  description = "Azure region for bootstrap resources."
  default     = "southeastasia"
}

variable "project_slug" {
  type        = string
  description = "Short lowercase project identifier."
  default     = "enterprise-rag"
}

variable "project_resource_group_name" {
  type        = string
  description = "Resource group managed by the platform Terraform stack."
  default     = "rg-enterprise-rag"
}

variable "state_resource_group_name" {
  type        = string
  description = "Resource group containing Terraform state storage."
  default     = "rg-enterprise-rag-tfstate"
}

variable "state_storage_account_name" {
  type        = string
  description = "Optional globally unique storage account name."
  default     = ""
}

variable "state_container_name" {
  type        = string
  description = "Blob container for Terraform state."
  default     = "tfstate"
}

variable "github_repository" {
  type        = string
  description = "GitHub repository in OWNER/REPOSITORY format."

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "github_repository must use OWNER/REPOSITORY format."
  }
}

variable "github_repository_owner_id" {
  type        = string
  description = "Immutable numeric GitHub owner ID used by the OIDC subject."

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_owner_id))
    error_message = "github_repository_owner_id must contain only digits."
  }
}

variable "github_repository_id" {
  type        = string
  description = "Immutable numeric GitHub repository ID used by the OIDC subject."

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must contain only digits."
  }
}

variable "github_environment" {
  type        = string
  description = "GitHub environment trusted by the Azure federated credential."
  default     = "production"
}
