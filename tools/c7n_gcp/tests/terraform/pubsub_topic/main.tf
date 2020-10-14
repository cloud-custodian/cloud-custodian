provider "google" {
  region = "us-east1"
}

resource "google_pubsub_topic" "test_topic" {
  name = "test_topic"
}
