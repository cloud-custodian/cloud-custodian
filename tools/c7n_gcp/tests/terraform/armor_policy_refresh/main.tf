provider "google" {}

resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_compute_security_policy" "default" {
  name = "c7n-armor-${terraform.workspace}-${random_id.suffix.hex}"

  rule {
    action   = "allow"
    priority = 2147483647

    match {
      versioned_expr = "SRC_IPS_V1"

      config {
        src_ip_ranges = ["*"]
      }
    }
  }

  labels = {
    env = "default"
  }
}
