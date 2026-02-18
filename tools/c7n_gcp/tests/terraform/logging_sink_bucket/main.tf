resource "random_pet" "server" {
}

resource "google_storage_bucket" "c7n" {
  name     = "${random_pet.server.id}-bucket"
  location = "us-central1"
  retention_policy {
    is_locked        = false
    retention_period = 111
  }
}

resource "google_logging_project_sink" "c7n" {
  name                   = "${random_pet.server.id}-sink"
  destination            = "storage.googleapis.com/${google_storage_bucket.c7n.name}"
  filter                 = "resource.type = gce_instance AND severity >= WARNING"
  unique_writer_identity = true

  depends_on = [
    google_storage_bucket.c7n
  ]
}

resource "google_project_iam_binding" "c7n" {
  project = "cloud-custodian"
  role    = "roles/storage.objectCreator"
  members = [
    google_logging_project_sink.c7n.writer_identity,
  ]
}
