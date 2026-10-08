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

resource "google_compute_health_check" "default" {
  name = "${local.prefix}-hc"

  tcp_health_check {
    port = 443
  }
}

resource "google_compute_backend_service" "default" {
  name                  = "${local.prefix}-bs"
  protocol              = "SSL"
  load_balancing_scheme = "EXTERNAL"
  health_checks         = [google_compute_health_check.default.id]
}

resource "google_compute_target_ssl_proxy" "weak" {
  name             = "${local.prefix}-ssl-weak"
  backend_service  = google_compute_backend_service.default.id
  ssl_certificates = [google_compute_ssl_certificate.default.id]
  ssl_policy       = google_compute_ssl_policy.weak.id
}
