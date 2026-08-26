resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_redis_instance" "default" {
  name           = "c7n-redis-${terraform.workspace}-${random_id.suffix.hex}"
  memory_size_gb = 1
  region         = "us-central1"
  tier           = "BASIC"

  labels = {
    env = "default"
  }
}
