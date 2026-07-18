provider "google" {}

resource "google_vertex_ai_endpoint" "central" {
  name         = "c7n-endpoint-central"
  display_name = "c7n-endpoint-central"
  location     = "us-central1"
  region       = "us-central1"
}

resource "google_vertex_ai_endpoint" "east" {
  name         = "c7n-endpoint-east"
  display_name = "c7n-endpoint-east"
  location     = "us-east1"
  region       = "us-east1"
}

