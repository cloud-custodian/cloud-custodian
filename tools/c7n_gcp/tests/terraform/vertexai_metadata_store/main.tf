provider "google" {}
provider "google-beta" {}

resource "google_vertex_ai_metadata_store" "central" {
  provider = google-beta
  name     = "c7n-test-metadata-store"
  region   = "us-central1"
}
