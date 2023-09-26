resource "random_pet" "c7n" {
  length = 1
}

resource "google_spanner_instance" "c7n" {
  name         = "${random_pet.c7n.id}-spanner-instance"
  display_name = "${random_pet.c7n.id}-spanner-instance"
  config       = "regional-us-central1"
  num_nodes    = 1
}

resource "google_spanner_database" "c7n" {
  instance            = google_spanner_instance.c7n.name
  name                = "${random_pet.c7n.id}-spanner-database"
  deletion_protection = false
}

resource "google_service_account" "c7n" {
  account_id   = "${random_pet.c7n.id}-sa"
  display_name = "${random_pet.c7n.id}-sa"
}

resource "null_resource" "c7n" {
  triggers = {
    spanner_instance = google_spanner_instance.c7n.name
    backup           = "${random_pet.c7n.id}-backup"
  }
  provisioner "local-exec" {
    when = create
    command = join(" ", [
      "gcloud spanner backups create ${self.triggers.backup}",
      "--instance=${google_spanner_instance.c7n.name}",
      "--database=${google_spanner_database.c7n.name}",
      "--retention-period=2w",
      "--async"
      ]
    )
  }
  provisioner "local-exec" {
    when = create
    command = join(" ", [
      "gcloud spanner backups add-iam-policy-binding ${self.triggers.backup}",
      "--instance=${google_spanner_instance.c7n.name}",
      "--member='serviceAccount:${google_service_account.c7n.email}'",
      "--role='roles/editor'"
      ]
    )
  }
  provisioner "local-exec" {
    when = destroy
    command = join(" ", [
      "gcloud spanner backups delete ${self.triggers.backup}",
      "--instance=${self.triggers.spanner_instance}",
      "--quiet"
      ]
    )
  }
  depends_on = [google_spanner_database.c7n]
}
