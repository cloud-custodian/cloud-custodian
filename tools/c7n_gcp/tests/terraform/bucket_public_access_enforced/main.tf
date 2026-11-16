provider "google" {}

resource "google_storage_bucket" "bucket" {
  name                        = "c7n-pap-test-k3v9xq2m"
  location                    = "US"
  force_destroy               = true
  public_access_prevention    = "inherited"
  uniform_bucket_level_access = true
}
