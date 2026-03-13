variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project               = var.google_project_id
  billing_project       = var.google_project_id
  user_project_override = true
}

output "project_id" {
  value = var.google_project_id
}
