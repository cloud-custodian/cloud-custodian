# Recording this fixture creates a management group, which is a tenant-level object,
# not a subscription one. The group is empty (no subscriptions, no policies) and the
# role in it is read-only and never assigned, but only record it in a dev tenant you're
# allowed to change. The tenant also needs management group hierarchy protection off:
# the recorder gets no role at the group except the Owner role Azure gives its creator.

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.9"
    }
  }
}

provider "azurerm" {
  features {}
}

data "azurerm_subscription" "current" {}

resource "azurerm_management_group" "test" {
  name         = "cctest-roledefinition-mg"
  display_name = "cctest-roledefinition-mg"
}

# The Owner role Azure gives the creator of a new management group can take a while
# to apply, and creating the role below needs it.
resource "time_sleep" "owner_propagation" {
  depends_on      = [azurerm_management_group.test]
  create_duration = "120s"
}

# Created at the management group, but also assignable at the subscription, so c7n
# lists it there with a /subscriptions/... id.
resource "azurerm_role_definition" "test" {
  name  = "cctest-roledefinition-mg"
  scope = azurerm_management_group.test.id

  permissions {
    actions = ["Microsoft.Resources/subscriptions/resourceGroups/read"]
  }

  assignable_scopes = [
    azurerm_management_group.test.id,
    data.azurerm_subscription.current.id,
  ]

  depends_on = [time_sleep.owner_propagation]
}
