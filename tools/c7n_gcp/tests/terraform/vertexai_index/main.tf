provider "google" {}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "google_vertex_ai_index" "central" {
  region              = "us-central1"
  display_name        = "c7n-test-index-central-${random_id.suffix.hex}"
  index_update_method = "STREAM_UPDATE"
  labels = {
    owner = "custodian"
  }

  metadata {
    config {
      dimensions            = 2
      distance_measure_type = "DOT_PRODUCT_DISTANCE"
      shard_size            = "SHARD_SIZE_SMALL"
      algorithm_config {
        brute_force_config {}
      }
    }
  }
}

resource "google_vertex_ai_index" "east" {
  region              = "us-east1"
  display_name        = "c7n-test-index-east-${random_id.suffix.hex}"
  index_update_method = "STREAM_UPDATE"

  metadata {
    config {
      dimensions            = 2
      distance_measure_type = "DOT_PRODUCT_DISTANCE"
      shard_size            = "SHARD_SIZE_SMALL"
      algorithm_config {
        brute_force_config {}
      }
    }
  }
}

resource "google_vertex_ai_index_endpoint" "central" {
  region                  = "us-central1"
  display_name            = "c7n-test-index-endpoint-${random_id.suffix.hex}"
  public_endpoint_enabled = true
}

resource "google_vertex_ai_index_endpoint_deployed_index" "central" {
  region            = "us-central1"
  index_endpoint    = google_vertex_ai_index_endpoint.central.id
  index             = google_vertex_ai_index.central.id
  deployed_index_id = "c7n_test_index_${random_id.suffix.hex}"

  dedicated_resources {
    machine_spec {
      machine_type = "e2-standard-2"
    }
    min_replica_count = 1
    max_replica_count = 1
  }
}

output "central_index_name" {
  value = google_vertex_ai_index.central.id
}

output "index_display_names" {
  value = {
    central = google_vertex_ai_index.central.display_name
    east    = google_vertex_ai_index.east.display_name
  }
}

output "deployed_index_id" {
  value = google_vertex_ai_index_endpoint_deployed_index.central.deployed_index_id
}
