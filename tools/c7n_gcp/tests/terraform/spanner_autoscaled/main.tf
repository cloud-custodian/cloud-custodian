provider "google" {}

resource "random_pet" "c7n" {
  length = 1
}

resource "google_spanner_instance" "c7n" {
  name         = "${random_pet.c7n.id}-spanner-au"
  display_name = "${random_pet.c7n.id}-spanner-au"
  config       = "regional-us-central1"
  # Managed autoscaling requires the ENTERPRISE edition or higher.
  edition = "ENTERPRISE"
  autoscaling_config {
    autoscaling_limits {
      min_nodes = 1
      max_nodes = 2
    }
    autoscaling_targets {
      total_cpu_utilization_percent = 80
      storage_utilization_percent   = 90
    }
  }
  labels = {
    env = "c7n-test"
  }
}
