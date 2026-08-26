resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_compute_disk" "default" {
  name = "c7n-disk-${terraform.workspace}-${random_id.suffix.hex}"
  type = "pd-standard"
  zone = "us-central1-a"
  size = 10
}

resource "google_compute_snapshot" "default" {
  name        = "c7n-snapshot-${terraform.workspace}-${random_id.suffix.hex}"
  source_disk = google_compute_disk.default.name
  zone        = google_compute_disk.default.zone

  labels = {
    env = "default"
  }
}
