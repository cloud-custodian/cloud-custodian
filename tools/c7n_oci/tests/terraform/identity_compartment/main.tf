variable "OCI_COMPARTMENT_ID" {
}

resource "oci_identity_compartment" "test_compartment" {
    compartment_id = var.OCI_COMPARTMENT_ID
    description = "Custodian Test"
    name = "Custodian-Test1"
    freeform_tags = {"Cloud_Custodian"= "True"}
}