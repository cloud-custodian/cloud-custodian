resource "random_id" "suffix" {
  byte_length = 2
}

locals {
  prefix = "c7n-${terraform.workspace}-${random_id.suffix.hex}"
}

resource "tls_private_key" "default" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_self_signed_cert" "default" {
  private_key_pem       = tls_private_key.default.private_key_pem
  validity_period_hours = 24
  allowed_uses          = ["key_encipherment", "digital_signature", "server_auth"]

  subject {
    common_name = "example.com"
  }
}

resource "google_compute_ssl_certificate" "default" {
  name        = "${local.prefix}-cert"
  private_key = tls_private_key.default.private_key_pem
  certificate = tls_self_signed_cert.default.cert_pem
}

resource "google_compute_ssl_policy" "weak" {
  name    = "${local.prefix}-weak"
  profile = "COMPATIBLE"
}

resource "google_compute_ssl_policy" "good" {
  name            = "${local.prefix}-good"
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
}

resource "google_storage_bucket" "default" {
  name                        = "${local.prefix}-lb-bucket"
  location                    = "US"
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_compute_backend_bucket" "default" {
  name        = "${local.prefix}-bb"
  bucket_name = google_storage_bucket.default.name
}

resource "google_compute_url_map" "default" {
  name            = "${local.prefix}-urlmap"
  default_service = google_compute_backend_bucket.default.id
}

resource "google_compute_target_https_proxy" "weak" {
  name             = "${local.prefix}-https-weak"
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_ssl_certificate.default.id]
  ssl_policy       = google_compute_ssl_policy.weak.id
}

resource "google_compute_target_https_proxy" "weak2" {
  name             = "${local.prefix}-https-weak2"
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_ssl_certificate.default.id]
  ssl_policy       = google_compute_ssl_policy.weak.id
}

resource "google_compute_target_https_proxy" "good" {
  name             = "${local.prefix}-https-good"
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_ssl_certificate.default.id]
  ssl_policy       = google_compute_ssl_policy.good.id
}

resource "google_compute_target_https_proxy" "none" {
  name             = "${local.prefix}-https-none"
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_ssl_certificate.default.id]
}
