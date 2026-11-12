provider "google" {
  region = "us-east1"
}

# Get the current project
data "google_project" "current" {
}

# Create a custom project-level IAM role for testing deletion
resource "google_project_iam_custom_role" "test_role" {
  role_id     = "customAccessContextManagerAdmin"
  title       = "Custom Access Context Manager Admin"
  description = "Custom role for testing Cloud Custodian delete action"

  permissions = [
    "accesscontextmanager.accessLevels.get",
    "accesscontextmanager.accessLevels.list",
  ]
}

output "role_id" {
  value = google_project_iam_custom_role.test_role.role_id
}

output "role_name" {
  value = google_project_iam_custom_role.test_role.name
}

output "project_id" {
  value = data.google_project.current.project_id
}
