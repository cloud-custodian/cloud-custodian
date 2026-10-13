provider "google" {}

data "google_project" "current" {}

resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_pubsub_topic" "dest" {
  name = "c7n-org-sink-${random_id.suffix.hex}"
}

# Disabled so the test never exports organization logs.
resource "google_logging_organization_sink" "all_entries" {
  name             = "c7n-org-all-${random_id.suffix.hex}"
  org_id           = data.google_project.current.org_id
  destination      = "pubsub.googleapis.com/${google_pubsub_topic.dest.id}"
  include_children = true
  disabled         = true
}

resource "google_logging_organization_sink" "filtered" {
  name        = "c7n-org-filtered-${random_id.suffix.hex}"
  org_id      = data.google_project.current.org_id
  destination = "pubsub.googleapis.com/${google_pubsub_topic.dest.id}"
  filter      = "severity >= ERROR"
  disabled    = true
}
