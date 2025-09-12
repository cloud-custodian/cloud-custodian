variable "OCI_COMPARTMENT_ID" {}

resource "oci_dns_view" "test_view" {
  #Required
  compartment_id = var.OCI_COMPARTMENT_ID

  #Optional
  scope        = "PRIVATE"
  display_name = "testview"
}

resource "oci_dns_zone" "test_zone" {
  #Required
  compartment_id = var.OCI_COMPARTMENT_ID
  name           = "testzone.com"
  zone_type      = "PRIMARY"
  scope          = "PRIVATE"
  view_id        = oci_dns_view.test_view.id
  freeform_tags  = { "Project" = "CNCF" }
}
