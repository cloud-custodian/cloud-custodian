provider "google" {}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "google_bigtable_instance" "instance" {
  name                = "c7n-gc-rule-${random_id.suffix.hex}"
  deletion_protection = false

  cluster {
    cluster_id   = "c7n-gc-cluster"
    zone         = "us-central1-a"
    num_nodes    = 1
    storage_type = "HDD"
  }
}

resource "google_bigtable_table" "gc_rule_table" {
  name          = "c7n-gc-table"
  instance_name = google_bigtable_instance.instance.name

  column_family {
    family = "cf_with_gc"
  }
}

resource "google_bigtable_gc_policy" "gc_rule_table_policy" {
  instance_name   = google_bigtable_instance.instance.name
  table           = google_bigtable_table.gc_rule_table.name
  column_family   = "cf_with_gc"
  deletion_policy = "ABANDON"

  max_age {
    duration = "86400s"
  }
}

resource "google_bigtable_table" "no_gc_rule_table" {
  name          = "c7n-no-gc-table"
  instance_name = google_bigtable_instance.instance.name

  column_family {
    family = "cf_no_gc"
  }
}
