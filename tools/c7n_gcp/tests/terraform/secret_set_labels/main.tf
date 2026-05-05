resource "google_secret_manager_secret" "secret" {
  secret_id = "c7n-secret"

  replication {
    auto {}
  }

  labels = {
    env = "default"
  }
}
