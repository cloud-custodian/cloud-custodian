provider "google" {
  region = "us-east1"
}

resource "google_pubsub_topic" "c7n" {
  name = "c7n-topic"
}

resource "google_pubsub_subscription" "c7n" {
  name  = "c7n-subscription"
  topic = google_pubsub_topic.c7n.name
}