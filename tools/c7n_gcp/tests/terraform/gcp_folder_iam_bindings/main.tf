# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

variable "parent_folder" {
  description = "Disposable test parent, in folders/<id> form"
  type        = string
}

variable "test_member" {
  description = "Existing test identity, in user:<email> form"
  type        = string
}

provider "google" {}

resource "google_folder" "test" {
  display_name        = "c7n-folder-bindings"
  parent              = var.parent_folder
  deletion_protection = false
}

resource "google_folder_iam_member" "preserved" {
  folder = google_folder.test.name
  role   = "roles/logging.viewer"
  member = var.test_member
}

resource "google_folder_iam_member" "removed" {
  folder = google_folder.test.name
  role   = "roles/viewer"
  member = var.test_member
}

resource "google_folder_iam_audit_config" "all_services" {
  folder  = google_folder.test.name
  service = "allServices"

  audit_log_config {
    log_type         = "DATA_WRITE"
    exempted_members = [var.test_member]
  }
}

resource "google_folder_iam_audit_config" "storage" {
  folder  = google_folder.test.name
  service = "storage.googleapis.com"

  audit_log_config {
    log_type         = "DATA_READ"
    exempted_members = [var.test_member]
  }
}
