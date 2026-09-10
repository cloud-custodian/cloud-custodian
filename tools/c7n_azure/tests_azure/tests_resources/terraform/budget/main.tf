provider "azurerm" {
  features {}
}

data "azurerm_subscription" "current" {}

resource "azurerm_consumption_budget_subscription" "budget_1000" {
  name            = "budget_1000"
  subscription_id = data.azurerm_subscription.current.id

  amount     = 1000
  time_grain = "Monthly"

  time_period {
    start_date = local.first_of_month
  }

  notification {
    enabled        = false
    threshold      = 90.0
    operator       = "EqualTo"
    contact_emails = ["test@example.com"]
  }
}

resource "azurerm_consumption_budget_subscription" "budget_1001" {
  name            = "budget_1001"
  subscription_id = data.azurerm_subscription.current.id

  amount     = 1001
  time_grain = "Monthly"

  time_period {
    start_date = local.first_of_month
  }

  notification {
    enabled        = false
    threshold      = 90.0
    operator       = "EqualTo"
    contact_emails = ["test@example.com"]
  }
}

locals {
  today          = timestamp()
  current_year   = formatdate("YYYY", local.today)
  current_month  = formatdate("MM", local.today)
  first_of_month = "${local.current_year}-${local.current_month}-01T00:00:00Z"
}


