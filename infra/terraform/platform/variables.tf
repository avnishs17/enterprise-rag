variable "location" {
  type        = string
  description = "Azure region for the AKS platform."
  default     = "southeastasia"
}

variable "project_slug" {
  type        = string
  description = "Short lowercase project identifier."
  default     = "enterprise-rag"
}

variable "project_resource_group_name" {
  type        = string
  description = "Existing resource group created by the bootstrap stack."
  default     = "rg-enterprise-rag"
}

variable "cluster_name" {
  type        = string
  description = "AKS cluster name."
  default     = "aks-enterprise-rag"
}

variable "acr_name" {
  type        = string
  description = "Optional globally unique alphanumeric ACR name."
  default     = ""
}

variable "key_vault_name" {
  type        = string
  description = "Optional globally unique Key Vault name."
  default     = ""
}

variable "node_vm_size" {
  type        = string
  description = "AKS system node VM size."
  default     = "Standard_B2s_v2"
}

variable "node_count" {
  type        = number
  description = "Initial number of AKS system nodes."
  default     = 1

  validation {
    condition     = var.node_count >= 1
    error_message = "node_count must be at least 1."
  }
}

variable "github_repository" {
  type        = string
  description = "GitHub repository in OWNER/REPOSITORY format."

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "github_repository must use OWNER/REPOSITORY format."
  }
}

variable "github_environment" {
  type        = string
  description = "GitHub environment trusted by the deployment identity."
  default     = "production"
}

variable "app_hostname" {
  type        = string
  description = "DNS hostname used by the AKS Ingress and application CORS settings."
}
