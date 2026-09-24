provider "google" {}


resource "google_spanner_instance" "c7n" {
  name         = "sbsi"
  display_name = "sbsi"
  config       = "regional-us-central1"
  num_nodes    = 1
}

resource "google_spanner_database" "c7n" {
  instance            = google_spanner_instance.c7n.name
  name                = "sbsd"
  deletion_protection = false
}

resource "google_spanner_backup_schedule" "c7n_long_retention" {
  instance           = google_spanner_instance.c7n.name
  database           = google_spanner_database.c7n.name
  name               = "sbsl"
  retention_duration = "2678400s"

  spec {
    cron_spec {
      text = "0 3 * * *"
    }
  }

  full_backup_spec {}

  depends_on = [google_spanner_database.c7n]
}
