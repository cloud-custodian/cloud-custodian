provider "google" {}
provider "google-beta" {}

# Short name: the region and "metadataStores" segments in the API path
# already push recorded flight-data filenames close to Windows' MAX_PATH,
# so keep this short (see vertexai_metadata_store_artifact_filtering test,
# which uses the always-present "default" store instead for the same reason).
resource "google_vertex_ai_metadata_store" "central" {
  provider = google-beta
  name     = "c7n-store"
  region   = "us-central1"
}
