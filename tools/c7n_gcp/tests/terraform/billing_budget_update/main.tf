variable "google_project_id" {
  description = "GCP project ID"
}

# The Billing Budgets API requires a quota project, and the provider only
# sends one when billing_project and user_project_override are set.
provider "google" {
  project               = var.google_project_id
  billing_project       = var.google_project_id
  user_project_override = true
}

# Budgets go on the billing account of the project the test runs against.
data "google_project" "this" {}

resource "random_id" "suffix" {
  byte_length = 3
}

resource "google_pubsub_topic" "alerts" {
  name = "c7n-bb-${random_id.suffix.hex}"
}

# Fixed amount on a calendar month: use-last-period-amount switches it.
resource "google_billing_budget" "lpa" {
  billing_account = data.google_project.this.billing_account
  display_name    = "c7n-bb-lpa-${random_id.suffix.hex}"

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "10"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
}

# Thresholds above weekly pacing: add-threshold appends 0.25 and keeps these.
resource "google_billing_budget" "thr" {
  billing_account = data.google_project.this.billing_account
  display_name    = "c7n-bb-thr-${random_id.suffix.hex}"

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "10"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.9
    spend_basis       = "FORECASTED_SPEND"
  }
}

resource "google_monitoring_notification_channel" "email" {
  display_name = "c7n-bb-${random_id.suffix.hex}"
  type         = "email"
  labels = {
    email_address = "c7n-bb@example.com"
  }
}

# Email route but no Pub/Sub route: pubsub-topic adds one. The email channel
# and disable_default_iam_recipients are the untouched siblings the nested
# updateMask must leave alone.
resource "google_billing_budget" "topic" {
  billing_account = data.google_project.this.billing_account
  display_name    = "c7n-bb-topic-${random_id.suffix.hex}"

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "10"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.email.id]
    disable_default_iam_recipients   = true
  }
}

# Custom period: the API rejects lastPeriodAmount here, so the action skips it.
resource "google_billing_budget" "custom" {
  billing_account = data.google_project.this.billing_account
  display_name    = "c7n-bb-custom-${random_id.suffix.hex}"

  budget_filter {
    custom_period {
      start_date {
        year  = 2026
        month = 1
        day   = 1
      }
    }
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "10"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
}
