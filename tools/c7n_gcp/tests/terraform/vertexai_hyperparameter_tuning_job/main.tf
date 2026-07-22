provider "google" {}

resource "random_id" "suffix" {
  byte_length = 2
}

output "job_display_name" {
  value = "c7n-test-hp-job-${terraform.workspace}-${random_id.suffix.hex}"
}
