provider "google" {}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "google_vertex_ai_index" "default" {
  region              = "us-central1"
  display_name        = "c7n-test-index-${random_id.suffix.hex}"
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

# Gets queries while the test records.
resource "google_vertex_ai_index_endpoint" "busy" {
  region                  = "us-central1"
  display_name            = "c7n-test-busy-${random_id.suffix.hex}"
  public_endpoint_enabled = true
}

resource "google_vertex_ai_index_endpoint_deployed_index" "busy" {
  region            = "us-central1"
  index_endpoint    = google_vertex_ai_index_endpoint.busy.id
  index             = google_vertex_ai_index.default.id
  deployed_index_id = "c7n_test_busy_${random_id.suffix.hex}"

  dedicated_resources {
    machine_spec {
      machine_type = "e2-standard-2"
    }
    min_replica_count = 1
    max_replica_count = 1
  }
}

# Deployed, but never queried.
resource "google_vertex_ai_index_endpoint" "idle" {
  region                  = "us-central1"
  display_name            = "c7n-test-idle-${random_id.suffix.hex}"
  public_endpoint_enabled = true
}

resource "google_vertex_ai_index_endpoint_deployed_index" "idle" {
  region            = "us-central1"
  index_endpoint    = google_vertex_ai_index_endpoint.idle.id
  index             = google_vertex_ai_index.default.id
  deployed_index_id = "c7n_test_idle_${random_id.suffix.hex}"

  dedicated_resources {
    machine_spec {
      machine_type = "e2-standard-2"
    }
    min_replica_count = 1
    max_replica_count = 1
  }
}

# Nothing deployed, so no replicas and nothing billed.
resource "google_vertex_ai_index_endpoint" "empty" {
  region                  = "us-central1"
  display_name            = "c7n-test-empty-${random_id.suffix.hex}"
  public_endpoint_enabled = true
}
