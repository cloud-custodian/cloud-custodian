provider "google" {}
provider "google-beta" {}

# Keep the name short: the region and "metadataStores" segments in the API
# path already push recorded flight-data filenames toward Windows' MAX_PATH.
resource "google_vertex_ai_metadata_store" "central" {
  provider = google-beta
  name     = "c7n-store"
  region   = "us-central1"
}
