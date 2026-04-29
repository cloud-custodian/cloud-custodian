resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_storage_bucket" "default" {
  name          = "c7n-lb-gfr-${terraform.workspace}-${random_id.suffix.hex}"
  location      = "US"
  force_destroy = true
}

resource "google_compute_backend_bucket" "default" {
  name        = "c7n-lb-bb-${terraform.workspace}-${random_id.suffix.hex}"
  bucket_name = google_storage_bucket.default.name
  enable_cdn  = false
}

resource "google_compute_url_map" "default" {
  name            = "c7n-lb-um-${terraform.workspace}-${random_id.suffix.hex}"
  default_service = google_compute_backend_bucket.default.id
}

resource "google_compute_target_http_proxy" "default" {
  name    = "c7n-lb-http-${terraform.workspace}-${random_id.suffix.hex}"
  url_map = google_compute_url_map.default.id
}

resource "google_compute_global_forwarding_rule" "default" {
  name        = "c7n-lb-gfr-${terraform.workspace}-${random_id.suffix.hex}"
  target      = google_compute_target_http_proxy.default.id
  port_range  = "80"
  ip_protocol = "TCP"

  labels = {
    env = "default"
  }
}
