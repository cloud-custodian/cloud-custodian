provider "google" {
  region = "us-east1"
}

# Get the current project
data "google_project" "current" {
}

# Create a custom IAM role for testing deletion
resource "google_project_iam_custom_role" "test_role" {
  role_id     = "custodianTestRole"
  title       = "Custodian Test Role"
  description = "A custom role for testing Cloud Custodian delete action"

  permissions = [
    "storage.buckets.list",
    "storage.buckets.get",
  ]
}

output "role_id" {
  value = google_project_iam_custom_role.test_role.role_id
}

output "role_name" {
  value = google_project_iam_custom_role.test_role.name
}

output "organization_id" {
  value = data.google_project.current.organization_id
}
