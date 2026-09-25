provider "google" {
  # Keep the provider's goog-terraform-provisioned label off, so the only
  # labels present are the ones under test.
  add_terraform_attribution_label = false
}

resource "random_id" "suffix" {
  byte_length = 2
}

# Positive: removal with a surviving label, the case that silently no-op'd
# when removed keys were omitted from a merge-patch body.
resource "google_dns_managed_zone" "partial" {
  name     = "c7n-remove-labels-partial-${random_id.suffix.hex}"
  dns_name = "c7n-remove-labels-partial-${random_id.suffix.hex}.example.com."

  labels = {
    c7n_keep     = "yes"
    c7n_remove_a = "a"
    c7n_remove_b = "b"
  }
}

# Positive: every label removed.
resource "google_dns_managed_zone" "full" {
  name     = "c7n-remove-labels-full-${random_id.suffix.hex}"
  dns_name = "c7n-remove-labels-full-${random_id.suffix.hex}.example.com."

  labels = {
    c7n_remove_a = "a"
    c7n_remove_b = "b"
  }
}

# Negative: none of the removed keys are present, labels must be untouched.
resource "google_dns_managed_zone" "absent" {
  name     = "c7n-remove-labels-absent-${random_id.suffix.hex}"
  dns_name = "c7n-remove-labels-absent-${random_id.suffix.hex}.example.com."

  labels = {
    c7n_keep = "yes"
  }
}
