provider "google" {}

resource "google_storage_bucket" "bucket" {
  name                        = "c7n-pap-inh-r7t2wd5n"
  location                    = "US"
  force_destroy               = true
  public_access_prevention    = "enforced"
  uniform_bucket_level_access = true
}
