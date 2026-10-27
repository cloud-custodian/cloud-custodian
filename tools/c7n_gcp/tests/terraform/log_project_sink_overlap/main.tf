variable "google_project_id" {
  description = "GCP project ID, for sink destinations"
}

provider "google" {}

locals {
  destination = "logging.googleapis.com/projects/${var.google_project_id}/locations/global/buckets/_Default"
}

resource "google_pubsub_topic" "other" {
  name = "c7n-sink-overlap-other"
}

resource "google_logging_project_sink" "base" {
  name        = "c7n-sink-overlap-base"
  destination = local.destination
  filter      = "severity>=ERROR"
}

resource "google_logging_project_sink" "base_copy" {
  name        = "c7n-sink-overlap-base-copy"
  destination = local.destination
  filter      = "severity>=ERROR"
}

resource "google_logging_project_sink" "subset" {
  name        = "c7n-sink-overlap-subset"
  destination = local.destination
  filter      = "severity>=CRITICAL"
}

resource "google_logging_project_sink" "not_clause" {
  name        = "c7n-sink-overlap-not-clause"
  destination = local.destination
  filter      = "severity>=ERROR AND NOT resource.type=\"gce_instance\""
}

resource "google_logging_project_sink" "exclusion_partial" {
  name        = "c7n-sink-overlap-excl-partial"
  destination = local.destination
  filter      = "severity>=ERROR"

  exclusions {
    name   = "gce"
    filter = "resource.type=\"gce_instance\""
  }
}

resource "google_logging_project_sink" "exclusion_all" {
  name        = "c7n-sink-overlap-excl-all"
  destination = local.destination
  filter      = "severity>=ERROR"

  exclusions {
    name   = "all"
    filter = "severity>=ERROR"
  }
}

resource "google_logging_project_sink" "non_match" {
  name        = "c7n-sink-overlap-non-match"
  destination = local.destination
  filter      = "severity<ERROR"
}

resource "google_logging_project_sink" "disabled" {
  name        = "c7n-sink-overlap-disabled"
  destination = local.destination
  filter      = "severity>=ERROR"
  disabled    = true
}

resource "google_logging_project_sink" "other_destination" {
  name        = "c7n-sink-overlap-other-dest"
  destination = "pubsub.googleapis.com/${google_pubsub_topic.other.id}"
  filter      = "severity>=ERROR"
}
