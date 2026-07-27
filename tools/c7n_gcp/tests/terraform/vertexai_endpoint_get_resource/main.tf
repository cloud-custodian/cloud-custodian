provider "google" {}

resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_vertex_ai_endpoint" "get_resource" {
  name         = "c7n-test-get-resource-${terraform.workspace}-${random_id.suffix.hex}"
  display_name = "c7n-test-get-resource-${terraform.workspace}-${random_id.suffix.hex}"
  location     = "us-central1"
  region       = "us-central1"
}

output "endpoint_name" {
  value       = google_vertex_ai_endpoint.get_resource.id
  description = "Full resource name of the test endpoint"
}

output "endpoint_display_name" {
  value       = google_vertex_ai_endpoint.get_resource.display_name
  description = "Display name of the test endpoint"
}
