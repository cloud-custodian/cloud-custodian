provider "google" {}

resource "random_pet" "c7n" {
  length = 1
}

resource "google_spanner_instance" "c7n" {
  name         = "${random_pet.c7n.id}-spanner-as"
  display_name = "${random_pet.c7n.id}-spanner-as"
  config       = "regional-us-central1"
  num_nodes    = 1
  # Managed autoscaling requires the ENTERPRISE edition or higher.
  edition = "ENTERPRISE"
  labels = {
    env = "c7n-test"
  }
}
