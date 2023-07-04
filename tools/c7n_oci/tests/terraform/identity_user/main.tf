variable "OCI_TENANCY_ID" {
}

resource "oci_identity_user" "test_user" {
  compartment_id = var.OCI_TENANCY_ID
  description    = "Test User1"
  name           = "Custodian_User"
  email          = "test@custodian.com"
  freeform_tags  = { "Cloud_Custodian" = "True" }
}

resource "oci_identity_auth_token" "test_auth_token1" {
  description = "Test user auth token"
  user_id     = oci_identity_user.test_user.id
}

resource "oci_identity_auth_token" "test_auth_token2" {
  description = "Test user auth token"
  user_id     = oci_identity_user.test_user.id
}

