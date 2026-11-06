variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project               = var.google_project_id
  billing_project       = var.google_project_id
  user_project_override = true
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "google_dataproc_cluster" "default" {
  name    = "c7n-test-${random_id.suffix.hex}"
  region  = "us-east1"
  project = var.google_project_id

  cluster_config {
    staging_bucket = null

    master_config {
      num_instances = 1
      machine_type  = "e2-medium"
      disk_config {
        boot_disk_size_gb = 30
      }
    }

    worker_config {
      num_instances = 2
      machine_type  = "e2-medium"
      disk_config {
        boot_disk_size_gb = 30
      }
    }

    gce_cluster_config {
      zone = "us-east1-b"
    }
  }
}
