variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

locals {
  destination = "logging.googleapis.com/projects/${var.google_project_id}/locations/global/buckets/_Default"
}

resource "google_logging_project_sink" "overlap_base" {
  name        = "c7n-sink-overlap-base"
  destination = local.destination
  filter      = "severity>=ERROR"
}

resource "google_logging_project_sink" "overlap_base_copy" {
  name        = "c7n-sink-overlap-base-copy"
  destination = local.destination
  filter      = "severity>=ERROR"
}

resource "google_logging_project_sink" "overlap_subset" {
  name        = "c7n-sink-overlap-subset"
  destination = local.destination
  filter      = "severity>=CRITICAL"
}

resource "google_logging_project_sink" "overlap_exclusion" {
  name        = "c7n-sink-overlap-exclusion"
  destination = local.destination
  filter      = "severity>=ERROR AND NOT resource.type=\"gce_instance\""
}

resource "google_logging_project_sink" "overlap_non_match" {
  name        = "c7n-sink-overlap-non-match"
  destination = local.destination
  filter      = "severity<ERROR"
}

resource "google_logging_project_sink" "overlap_disabled" {
  name        = "c7n-sink-overlap-disabled"
  destination = local.destination
  filter      = "severity>=ERROR"
  disabled    = true
}
