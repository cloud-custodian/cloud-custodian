# Terraform configuration for Azure Blob Storage testing
# Creates test storage account and blobs for Cloud Custodian value_from filter testing

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# Generate random suffix for unique naming
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

# Get current subscription for resource group location
data "azurerm_subscription" "current" {}

# Create resource group for test storage
resource "azurerm_resource_group" "test" {
  name     = "c7n-resolver-test-${random_string.suffix.result}"
  location = "East US"

  tags = {
    purpose   = "c7n-testing"
    component = "azure-blob-resolver"
  }
}

# Create storage account for blob storage tests
resource "azurerm_storage_account" "test" {
  name                     = "c7ntest${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.test.name
  location                 = azurerm_resource_group.test.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  # Allow blob public access for testing (can be set to false for authenticated-only testing)
  allow_nested_items_to_be_public = false

  tags = {
    purpose   = "c7n-testing"
    component = "azure-blob-resolver"
  }
}

# Create container for test blobs
resource "azurerm_storage_container" "test" {
  name                  = "test-configs"
  storage_account_name  = azurerm_storage_account.test.name
  container_access_type = "private"
}

# Create nested container for path testing
resource "azurerm_storage_container" "nested" {
  name                  = "nested-paths"
  storage_account_name  = azurerm_storage_account.test.name
  container_access_type = "private"
}

# Test Blob 1: JSON file with array of VM names
resource "azurerm_storage_blob" "json_simple" {
  name                   = "approved-vms.json"
  storage_account_name   = azurerm_storage_account.test.name
  storage_container_name = azurerm_storage_container.test.name
  type                   = "Block"
  source_content = jsonencode([
    "vm-prod-web-01",
    "vm-prod-web-02",
    "vm-prod-db-01"
  ])
  content_type = "application/json"
}

# Test Blob 2: JSON file with complex structure (for JMESPath testing)
resource "azurerm_storage_blob" "json_complex" {
  name                   = "vm-config.json"
  storage_account_name   = azurerm_storage_account.test.name
  storage_container_name = azurerm_storage_container.test.name
  type                   = "Block"
  source_content = jsonencode({
    vms = [
      {
        vmName = "vm-prod-web-01"
        region = "eastus"
        tags = {
          environment = "production"
          tier        = "web"
        }
      },
      {
        vmName = "vm-prod-web-02"
        region = "eastus"
        tags = {
          environment = "production"
          tier        = "web"
        }
      },
      {
        vmName = "vm-prod-db-01"
        region = "eastus"
        tags = {
          environment = "production"
          tier        = "database"
        }
      }
    ]
  })
  content_type = "application/json"
}

# Test Blob 3: CSV file
resource "azurerm_storage_blob" "csv" {
  name                   = "resource-groups.csv"
  storage_account_name   = azurerm_storage_account.test.name
  storage_container_name = azurerm_storage_container.test.name
  type                   = "Block"
  source_content         = <<-EOT
name,location,environment
rg-prod-web,eastus,production
rg-prod-db,eastus,production
rg-dev-web,westus,development
EOT
  content_type           = "text/csv"
}

# Test Blob 4: Plain text file
resource "azurerm_storage_blob" "txt" {
  name                   = "vm-ids.txt"
  storage_account_name   = azurerm_storage_account.test.name
  storage_container_name = azurerm_storage_container.test.name
  type                   = "Block"
  source_content         = <<-EOT
/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1
/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm2
/subscriptions/sub1/resourceGroups/rg2/providers/Microsoft.Compute/virtualMachines/vm3
EOT
  content_type           = "text/plain"
}

# Test Blob 5: Compressed JSON file (.gz)
# Note: Azure Blob Storage stores the actual compressed bytes
resource "azurerm_storage_blob" "json_compressed" {
  name                   = "compressed-vms.json.gz"
  storage_account_name   = azurerm_storage_account.test.name
  storage_container_name = azurerm_storage_container.test.name
  type                   = "Block"
  # For this test, we'll create a simple JSON and let the test handle compression
  # In real usage, this would be actual gzipped content
  source_content = jsonencode([
    "vm-compressed-01",
    "vm-compressed-02",
    "vm-compressed-03"
  ])
  content_type = "application/gzip"
}

# Test Blob 6: Nested path JSON file
resource "azurerm_storage_blob" "nested_json" {
  name                   = "configs/prod/allowed-regions.json"
  storage_account_name   = azurerm_storage_account.test.name
  storage_container_name = azurerm_storage_container.nested.name
  type                   = "Block"
  source_content = jsonencode([
    "eastus",
    "westus",
    "centralus"
  ])
  content_type = "application/json"
}

# Test Blob 7: Empty JSON array (edge case)
resource "azurerm_storage_blob" "json_empty" {
  name                   = "empty-list.json"
  storage_account_name   = azurerm_storage_account.test.name
  storage_container_name = azurerm_storage_container.test.name
  type                   = "Block"
  source_content         = "[]"
  content_type           = "application/json"
}

# Outputs for test consumption
output "storage_account_name" {
  value       = azurerm_storage_account.test.name
  description = "Name of the test storage account"
}

output "storage_account_url" {
  value       = azurerm_storage_account.test.primary_blob_endpoint
  description = "Primary blob endpoint URL"
}

output "container_name" {
  value       = azurerm_storage_container.test.name
  description = "Name of the test container"
}

output "nested_container_name" {
  value       = azurerm_storage_container.nested.name
  description = "Name of the nested paths container"
}

output "resource_group_name" {
  value       = azurerm_resource_group.test.name
  description = "Name of the test resource group"
}

output "blob_json_simple" {
  value = {
    name           = azurerm_storage_blob.json_simple.name
    url            = "azure://${azurerm_storage_account.test.name}.blob.core.windows.net/${azurerm_storage_container.test.name}/${azurerm_storage_blob.json_simple.name}"
    content_sample = ["vm-prod-web-01", "vm-prod-web-02", "vm-prod-db-01"]
  }
  description = "Simple JSON blob details"
}

output "blob_json_complex" {
  value = {
    name = azurerm_storage_blob.json_complex.name
    url  = "azure://${azurerm_storage_account.test.name}.blob.core.windows.net/${azurerm_storage_container.test.name}/${azurerm_storage_blob.json_complex.name}"
  }
  description = "Complex JSON blob details"
}

output "blob_csv" {
  value = {
    name = azurerm_storage_blob.csv.name
    url  = "azure://${azurerm_storage_account.test.name}.blob.core.windows.net/${azurerm_storage_container.test.name}/${azurerm_storage_blob.csv.name}"
  }
  description = "CSV blob details"
}

output "blob_txt" {
  value = {
    name = azurerm_storage_blob.txt.name
    url  = "azure://${azurerm_storage_account.test.name}.blob.core.windows.net/${azurerm_storage_container.test.name}/${azurerm_storage_blob.txt.name}"
  }
  description = "Text blob details"
}

output "blob_compressed" {
  value = {
    name = azurerm_storage_blob.json_compressed.name
    url  = "azure://${azurerm_storage_account.test.name}.blob.core.windows.net/${azurerm_storage_container.test.name}/${azurerm_storage_blob.json_compressed.name}"
  }
  description = "Compressed JSON blob details"
}

output "blob_nested" {
  value = {
    name = azurerm_storage_blob.nested_json.name
    url  = "azure://${azurerm_storage_account.test.name}.blob.core.windows.net/${azurerm_storage_container.nested.name}/${azurerm_storage_blob.nested_json.name}"
  }
  description = "Nested path blob details"
}

output "blob_empty" {
  value = {
    name = azurerm_storage_blob.json_empty.name
    url  = "azure://${azurerm_storage_account.test.name}.blob.core.windows.net/${azurerm_storage_container.test.name}/${azurerm_storage_blob.json_empty.name}"
  }
  description = "Empty JSON array blob details"
}
