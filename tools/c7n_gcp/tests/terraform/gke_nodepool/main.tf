provider "google" {
  region = "us-central1"
}

resource "random_pet" "cluster_name" {
  length = 2
}

# Create a GKE cluster first
resource "google_container_cluster" "test_cluster" {
  name     = "c7n-test-cluster-${random_pet.cluster_name.id}"
  location = "us-central1-a"

  # We can't create a cluster without a node pool defined
  # but we want to create a separate node pool for testing deletion
  remove_default_node_pool = true
  initial_node_count       = 1
}

# Create a separate node pool to test deletion
resource "google_container_node_pool" "test_nodepool" {
  name       = "custodian-nodepool-delete-test"
  location   = "us-central1-a"
  cluster    = google_container_cluster.test_cluster.name
  node_count = 1

  node_config {
    machine_type = "e2-medium"
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}

output "cluster_name" {
  value = google_container_cluster.test_cluster.name
}

output "nodepool_name" {
  value = google_container_node_pool.test_nodepool.name
}

output "location" {
  value = google_container_cluster.test_cluster.location
}
