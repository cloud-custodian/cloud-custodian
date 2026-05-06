resource "random_id" "suffix" {
  byte_length = 2
}

data "google_project" "current" {}

data "archive_file" "function_source" {
  type        = "zip"
  source_dir  = "${path.module}/source"
  output_path = "${path.module}/.terraform/function.zip"
}

resource "google_storage_bucket" "source" {
  name                        = "c7n-function-${terraform.workspace}-${random_id.suffix.hex}"
  location                    = "US"
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_object" "source" {
  name   = "function-${data.archive_file.function_source.output_md5}.zip"
  bucket = google_storage_bucket.source.name
  source = data.archive_file.function_source.output_path
}

# Perms required to provision the function
resource "google_project_iam_member" "cloudfunctions_artifactregistry_reader" {
  project = data.google_project.current.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:service-${data.google_project.current.number}@gcf-admin-robot.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "compute_storage_object_viewer" {
  project = data.google_project.current.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "compute_artifactregistry_writer" {
  project = data.google_project.current.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Makes sure logs get written in the event of a build error, for troubleshooting
resource "google_project_iam_member" "compute_logs_writer" {
  project = data.google_project.current.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "time_sleep" "iam_propagation" {
  create_duration = "90s"

  depends_on = [
    google_project_iam_member.cloudfunctions_artifactregistry_reader,
    google_project_iam_member.compute_artifactregistry_writer,
    google_project_iam_member.compute_logs_writer,
    google_project_iam_member.compute_storage_object_viewer,
  ]
}

resource "google_cloudfunctions_function" "default" {
  name                  = "c7n-function-${terraform.workspace}-${random_id.suffix.hex}"
  region                = "us-central1"
  runtime               = "python310"
  available_memory_mb   = 128
  source_archive_bucket = google_storage_bucket.source.name
  source_archive_object = google_storage_bucket_object.source.name
  trigger_http          = true
  entry_point           = "hello_http"

  labels = {
    env = "default"
  }

  depends_on = [
    time_sleep.iam_propagation,
  ]
}
