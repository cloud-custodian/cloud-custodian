resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_pubsub_topic" "default" {
  name = "c7n-topic-${terraform.workspace}-${random_id.suffix.hex}"
}

resource "google_pubsub_subscription" "default" {
  name  = "c7n-subscription-${terraform.workspace}-${random_id.suffix.hex}"
  topic = google_pubsub_topic.default.name

  labels = {
    env = "default"
  }
}
