variable "OCI_TENANCY_ID" {
}

resource "oci_identity_group" "test_group" {
  compartment_id = var.OCI_TENANCY_ID
  description    = "Custodian Test"
  name           = "Custodian-Dev-Group"
  freeform_tags  = { "Cloud_Custodian" = "Present" }
}