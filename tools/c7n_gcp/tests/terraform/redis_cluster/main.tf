terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "google" {}
provider "google-beta" {}

data "google_project" "current" {}

resource "google_project_service" "networkconnectivity_api" {
  project            = data.google_project.current.project_id
  service            = "networkconnectivity.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "serviceconsumermanagement_api" {
  project            = data.google_project.current.project_id
  service            = "serviceconsumermanagement.googleapis.com"
  disable_on_destroy = false
}

resource "google_compute_network" "producer_net" {
  name                    = "c7n-redis-cluster-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "producer_subnet_central" {
  name          = "c7n-redis-subnet-central"
  ip_cidr_range = "10.90.0.0/29"
  region        = "us-central1"
  network       = google_compute_network.producer_net.id
}

resource "google_compute_subnetwork" "producer_subnet_east" {
  name          = "c7n-redis-subnet-east"
  ip_cidr_range = "10.90.0.8/29"
  region        = "us-east1"
  network       = google_compute_network.producer_net.id
}

resource "google_network_connectivity_service_connection_policy" "memorystore_policy_central" {
  provider      = google-beta
  name          = "c7n-redis-policy-central"
  location      = "us-central1"
  service_class = "gcp-memorystore-redis"
  description   = "Cloud Custodian test policy for Redis Cluster (us-central1)"
  network       = google_compute_network.producer_net.id

  psc_config {
    subnetworks = [google_compute_subnetwork.producer_subnet_central.id]
  }

  depends_on = [
    google_project_service.networkconnectivity_api,
    google_project_service.serviceconsumermanagement_api,
  ]
}

resource "google_network_connectivity_service_connection_policy" "memorystore_policy_east" {
  provider      = google-beta
  name          = "c7n-redis-policy-east"
  location      = "us-east1"
  service_class = "gcp-memorystore-redis"
  description   = "Cloud Custodian test policy for Redis Cluster (us-east1)"
  network       = google_compute_network.producer_net.id

  psc_config {
    subnetworks = [google_compute_subnetwork.producer_subnet_east.id]
  }

  depends_on = [
    google_project_service.networkconnectivity_api,
    google_project_service.serviceconsumermanagement_api,
  ]
}

resource "google_redis_cluster" "c7n_redis_cluster_primary" {
  provider                    = google-beta
  name                        = "c7n-redis-cluster-primary"
  region                      = "us-central1"
  node_type                   = "REDIS_SHARED_CORE_NANO"
  shard_count                 = 3
  replica_count               = 1
  authorization_mode          = "AUTH_MODE_IAM_AUTH"
  transit_encryption_mode     = "TRANSIT_ENCRYPTION_MODE_SERVER_AUTHENTICATION"
  deletion_protection_enabled = false

  psc_configs {
    network = google_compute_network.producer_net.id
  }

  depends_on = [google_network_connectivity_service_connection_policy.memorystore_policy_central]
}

resource "google_redis_cluster" "c7n_redis_cluster_legacy" {
  provider                    = google-beta
  name                        = "c7n-redis-cluster-legacy"
  region                      = "us-east1"
  node_type                   = "REDIS_SHARED_CORE_NANO"
  shard_count                 = 3
  replica_count               = 1
  authorization_mode          = "AUTH_MODE_DISABLED"
  transit_encryption_mode     = "TRANSIT_ENCRYPTION_MODE_DISABLED"
  deletion_protection_enabled = false

  psc_configs {
    network = google_compute_network.producer_net.id
  }

  depends_on = [google_network_connectivity_service_connection_policy.memorystore_policy_east]
}
