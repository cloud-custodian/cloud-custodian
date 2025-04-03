resource "azurerm_resource_group" "rg" {
  name     = "use"
  location = "East US"
}

resource "azurerm_storage_account" "multiple_references" {
  name                          = "multiple-references"
  public_network_access_enabled = "false"
}

resource "azurerm_private_endpoint" "multiple_references" {
  name = "multiple-references"

  private_service_connection {
    name                           = "multiple-references"
    private_connection_resource_id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/${azurerm_resource_group.rg.name}/providers/Microsoft.Storage/storageAccounts/${azurerm_storage_account.multiple_references.name}"
  }
}

resource "azurerm_storage_account" "single_reference" {
  name                          = "private"
  public_network_access_enabled = "false"
}

resource "azurerm_private_endpoint" "single_reference" {
  name = "with-single-reference"

  private_service_connection {
    name                           = "single-reference"
    private_connection_resource_id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/use/providers/Microsoft.Storage/storageAccounts/${azurerm_storage_account.single_reference.name}"
  }
}
