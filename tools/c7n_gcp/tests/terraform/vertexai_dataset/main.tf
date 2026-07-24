provider "google" {}

resource "google_vertex_ai_dataset" "central" {
  display_name        = "c7n-test-dataset-central"
  metadata_schema_uri = "gs://google-cloud-aiplatform/schema/dataset/metadata/image_1.0.0.yaml"
  region              = "us-central1"

  labels = {
    env = "test"
  }
}

resource "google_vertex_ai_dataset" "east" {
  display_name        = "c7n-test-dataset-east"
  metadata_schema_uri = "gs://google-cloud-aiplatform/schema/dataset/metadata/tabular_1.0.0.yaml"
  region              = "us-east1"

  labels = {
    env = "test"
  }
}
