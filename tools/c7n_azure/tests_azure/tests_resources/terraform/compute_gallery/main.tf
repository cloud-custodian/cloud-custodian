# Terraform configuration for Compute Gallery testing
# Creates test galleries, images, and versions for Cloud Custodian policy testing

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

# Get current subscription data
data "azurerm_client_config" "current" {}
data "azurerm_subscription" "current" {}

# Create resource group for test resources
resource "azurerm_resource_group" "test" {
  name     = "c7n-test-gallery-${random_string.suffix.result}"
  location = "West Europe"
}

# Test Gallery 1: Main test gallery
resource "azurerm_shared_image_gallery" "test_gallery" {
  name                = "c7ntestgallery${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.test.name
  location            = azurerm_resource_group.test.location
  description         = "C7N Test Compute Gallery"

  tags = {
    Environment = "Test"
    Purpose     = "CloudCustodian"
  }
}

# Test Gallery 2: Secondary gallery for filter testing
resource "azurerm_shared_image_gallery" "secondary_gallery" {
  name                = "c7nsecondary${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.test.name
  location            = azurerm_resource_group.test.location
  description         = "C7N Secondary Test Gallery"

  tags = {
    Environment = "Test"
    Purpose     = "FilterTesting"
  }
}

# Image Definition 1: Linux image
resource "azurerm_shared_image" "linux_image" {
  name                = "c7n-linux-image"
  gallery_name        = azurerm_shared_image_gallery.test_gallery.name
  resource_group_name = azurerm_resource_group.test.name
  location            = azurerm_resource_group.test.location
  os_type             = "Linux"

  identifier {
    publisher = "C7N"
    offer     = "TestLinux"
    sku       = "v1"
  }

  tags = {
    OSType = "Linux"
  }
}

# Image Definition 2: Windows image
resource "azurerm_shared_image" "windows_image" {
  name                = "c7n-windows-image"
  gallery_name        = azurerm_shared_image_gallery.test_gallery.name
  resource_group_name = azurerm_resource_group.test.name
  location            = azurerm_resource_group.test.location
  os_type             = "Windows"

  identifier {
    publisher = "C7N"
    offer     = "TestWindows"
    sku       = "v1"
  }

  tags = {
    OSType = "Windows"
  }
}

# Image Definition 3: Image in secondary gallery
resource "azurerm_shared_image" "secondary_image" {
  name                = "c7n-secondary-image"
  gallery_name        = azurerm_shared_image_gallery.secondary_gallery.name
  resource_group_name = azurerm_resource_group.test.name
  location            = azurerm_resource_group.test.location
  os_type             = "Linux"

  identifier {
    publisher = "C7N"
    offer     = "Secondary"
    sku       = "v1"
  }
}

# Outputs for test assertions
output "resource_group_name" {
  value = azurerm_resource_group.test.name
}

output "test_gallery" {
  value = {
    name     = azurerm_shared_image_gallery.test_gallery.name
    id       = azurerm_shared_image_gallery.test_gallery.id
    location = azurerm_shared_image_gallery.test_gallery.location
  }
}

output "secondary_gallery" {
  value = {
    name     = azurerm_shared_image_gallery.secondary_gallery.name
    id       = azurerm_shared_image_gallery.secondary_gallery.id
    location = azurerm_shared_image_gallery.secondary_gallery.location
  }
}

output "linux_image" {
  value = {
    name    = azurerm_shared_image.linux_image.name
    id      = azurerm_shared_image.linux_image.id
    os_type = azurerm_shared_image.linux_image.os_type
    gallery = azurerm_shared_image_gallery.test_gallery.name
  }
}

output "windows_image" {
  value = {
    name    = azurerm_shared_image.windows_image.name
    id      = azurerm_shared_image.windows_image.id
    os_type = azurerm_shared_image.windows_image.os_type
    gallery = azurerm_shared_image_gallery.test_gallery.name
  }
}

output "secondary_image" {
  value = {
    name    = azurerm_shared_image.secondary_image.name
    id      = azurerm_shared_image.secondary_image.id
    os_type = azurerm_shared_image.secondary_image.os_type
    gallery = azurerm_shared_image_gallery.secondary_gallery.name
  }
}
