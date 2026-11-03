provider "google" {}

# Two locations, so the `locations/-` listing has to cover more than one.
# Keep ids short: they appear in recorded flight-data filenames.
resource "google_vector_search_collection" "busy" {
  location      = "us-central1"
  collection_id = "c7n-active"
  display_name  = "c7n active collection"
  labels = {
    env = "c7n"
  }

  vector_schema {
    field_name = "emb"
    dense_vector {
      dimensions = 3
    }
  }
}

resource "google_vector_search_collection" "idle" {
  location      = "us-east1"
  collection_id = "c7n-unused"
  display_name  = "c7n unused collection"

  vector_schema {
    field_name = "emb"
    dense_vector {
      dimensions = 3
    }
  }
}

# Data for the recording-time reads to find.
resource "google_vector_search_data_object" "book" {
  location       = google_vector_search_collection.busy.location
  collection_id  = google_vector_search_collection.busy.collection_id
  data_object_id = "book1"
  data           = jsonencode({})

  vectors {
    field_name = "emb"
    dense {
      values = [1, 0, 0]
    }
  }
}

# The index is listed as soon as it's accepted, so skip the ~45 minute build.
# Deleting it waits for the build, hence the longer delete timeout.
resource "google_vector_search_index" "busy" {
  location      = google_vector_search_collection.busy.location
  collection_id = google_vector_search_collection.busy.collection_id
  index_id      = "c7n-idx"
  index_field   = "emb"
  skip_wait     = true

  dedicated_infrastructure {
    autoscaling_spec {
      min_replica_count = 1
      max_replica_count = 1
    }
  }

  timeouts {
    delete = "120m"
  }
}

output "busy_name" {
  value = google_vector_search_collection.busy.name
}

output "idle_name" {
  value = google_vector_search_collection.idle.name
}
