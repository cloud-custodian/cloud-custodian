variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "google_bigtable_instance" "instance" {
  name                = "c7n-bigtable-instance"
  deletion_protection = false

  cluster {
    cluster_id   = "c7n-bigtable-cluster"
    zone         = "us-central1-a"
    num_nodes    = 1
    storage_type = "HDD"
  }

  labels = {
    env = "default"
  }
}
