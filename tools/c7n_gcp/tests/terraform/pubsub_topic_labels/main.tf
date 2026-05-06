resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_pubsub_topic" "default" {
  name = "c7n-topic-${terraform.workspace}-${random_id.suffix.hex}"

  labels = {
    env = "default"
  }
}
