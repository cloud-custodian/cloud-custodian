provider "google" {
  region = "us-east1"
}

# Get the current project, to find its parent organization
data "google_project" "current" {
}

# Create a custom organization-level IAM role for testing deletion
resource "google_organization_iam_custom_role" "test_role" {
  org_id      = data.google_project.current.org_id
  role_id     = "customAccessContextManagerAdmin"
  title       = "Custom Access Context Manager Admin"
  description = "Custom role for testing Cloud Custodian delete action"

  permissions = [
    "accesscontextmanager.accessLevels.get",
    "accesscontextmanager.accessLevels.list",
  ]
}

output "role_id" {
  value = google_organization_iam_custom_role.test_role.role_id
}

output "role_name" {
  value = google_organization_iam_custom_role.test_role.name
}

output "organization_id" {
  value = data.google_project.current.org_id
}
