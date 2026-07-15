provider "google" {}

resource "google_artifact_registry_repository" "c7n_artifact_repo" {
  location      = "us-central1"
  repository_id = "c7n-artifact-repo"
  description   = "Cloud Custodian test artifact repository"
  format        = "DOCKER"

  labels = {
    env = "default"
  }
}

