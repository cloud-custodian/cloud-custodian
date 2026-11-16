variable "google_project_id" {
  description = "GCP project ID, for sink destinations"
}

provider "google" {}

locals {
  destination = "logging.googleapis.com/projects/${var.google_project_id}/locations/global/buckets/_Default"
}

resource "google_pubsub_topic" "other" {
  name = "c7n-sink-exact-other"
}

resource "google_logging_project_sink" "a" {
  name        = "c7n-sink-exact-a"
  destination = local.destination
  filter      = "severity>=ERROR AND resource.type=\"gce_instance\""
}

resource "google_logging_project_sink" "b" {
  name        = "c7n-sink-exact-b"
  destination = local.destination
  filter      = "resource.type=\"gce_instance\" AND severity>=ERROR"
}

resource "google_logging_project_sink" "non_match" {
  name        = "c7n-sink-exact-non-match"
  destination = local.destination
  filter      = "severity>=WARNING AND resource.type=\"gce_instance\""
}

resource "google_logging_project_sink" "disabled" {
  name        = "c7n-sink-exact-disabled"
  destination = local.destination
  filter      = "severity>=ERROR AND resource.type=\"gce_instance\""
  disabled    = true
}

resource "google_logging_project_sink" "with_exclusion" {
  name        = "c7n-sink-exact-with-exclusion"
  destination = local.destination
  filter      = "severity>=ERROR AND resource.type=\"gce_instance\""

  exclusions {
    name   = "zone"
    filter = "resource.labels.zone=\"us-east1-b\""
  }
}

resource "google_logging_project_sink" "other_destination" {
  name        = "c7n-sink-exact-other-dest"
  destination = "pubsub.googleapis.com/${google_pubsub_topic.other.id}"
  filter      = "severity>=ERROR AND resource.type=\"gce_instance\""
}

resource "google_logging_project_sink" "no_filter_a" {
  name        = "c7n-sink-exact-no-filter-a"
  destination = local.destination
}

resource "google_logging_project_sink" "no_filter_b" {
  name        = "c7n-sink-exact-no-filter-b"
  destination = local.destination
}
