variable "OCI_COMPARTMENT_ID" {}

data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.OCI_COMPARTMENT_ID
}

resource "oci_objectstorage_bucket" "test_bucket" {
  compartment_id = var.OCI_COMPARTMENT_ID
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "test_bucket"
  access_type    = "ObjectRead"
  auto_tiering   = "Disabled"
  freeform_tags  = { "Project" = "CNCF" }
}