variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

locals {
  destination = "logging.googleapis.com/projects/${var.google_project_id}/locations/global/buckets/_Default"
}

resource "google_logging_project_sink" "exact_a" {
  name        = "c7n-sink-exact-a"
  destination = local.destination
  filter      = "severity>=ERROR AND resource.type=\"gce_instance\""
}

resource "google_logging_project_sink" "exact_b" {
  name        = "c7n-sink-exact-b"
  destination = local.destination
  filter      = "resource.type=\"gce_instance\" AND severity>=ERROR"
}

resource "google_logging_project_sink" "exact_non_match" {
  name        = "c7n-sink-exact-non-match"
  destination = local.destination
  filter      = "severity>=WARNING AND resource.type=\"gce_instance\""
}

resource "google_logging_project_sink" "exact_disabled" {
  name        = "c7n-sink-exact-disabled"
  destination = local.destination
  filter      = "severity>=ERROR AND resource.type=\"gce_instance\""
  disabled    = true
}

resource "google_logging_project_sink" "exact_no_filter_a" {
  name        = "c7n-sink-exact-no-filter-a"
  destination = local.destination
}

resource "google_logging_project_sink" "exact_no_filter_b" {
  name        = "c7n-sink-exact-no-filter-b"
  destination = local.destination
}
