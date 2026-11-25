provider "google" {
  region = "us-east1"
}

resource "random_pet" "bucket_name" {
  length = 2
}

resource "google_storage_bucket" "test_bucket" {
  name     = "c7n-bucket-delete-test-${random_pet.bucket_name.id}"
  location = "US-EAST1"

  force_destroy = true

  uniform_bucket_level_access = false
}

output "bucket_name" {
  value = google_storage_bucket.test_bucket.name
}
