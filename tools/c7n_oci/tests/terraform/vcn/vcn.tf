# For more examples like this please refer to https://github.com/oracle/terraform-provider-oci/tree/master/examples
variable "OCI_COMPARTMENT_ID" {}

resource "oci_core_vcn" "test_virtual_network_vcn" {
  cidr_block     = "10.1.0.0/16"
  compartment_id = var.OCI_COMPARTMENT_ID
  display_name   = "TestVcn"
  dns_label      = "TestVcn"
  freeform_tags  = { "Project" = "CNCF" }
}