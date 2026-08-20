resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_compute_region_disk" "default" {
  name          = "c7n-regional-audit-${terraform.workspace}-${random_id.suffix.hex}"
  region        = "us-central1"
  type          = "pd-ssd"
  size          = 10
  replica_zones = ["us-central1-a", "us-central1-b"]
}

output "disk_name" {
  value       = google_compute_region_disk.default.name
  description = "Name of the test regional disk"
}

output "region" {
  value       = google_compute_region_disk.default.region
  description = "Region of the test regional disk"
}
