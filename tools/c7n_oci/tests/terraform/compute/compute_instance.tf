# For more examples like this please refer to https://github.com/oracle/terraform-provider-oci/tree/master/examples

variable "num_instances" {
  default = "1"
}

variable "num_iscsi_volumes_per_instance" {
  default = "1"
}

variable "num_paravirtualized_volumes_per_instance" {
  default = "1"
}
variable "instance_ocpus" {
  default = 1
}

variable "instance_shape_config_memory_in_gbs" {
  default = 1
}

variable "OCI_COMPARTMENT_ID" {}
variable "OCI_COMPUTE_IMAGE_ID" {}

data "oci_identity_availability_domain" "ad" {
  compartment_id = var.OCI_COMPARTMENT_ID
  ad_number      = 1
}

resource "oci_core_vcn" "test_vcn" {
  cidr_block     = "10.1.0.0/16"
  compartment_id = var.OCI_COMPARTMENT_ID
  display_name   = "TestVcn"
  dns_label      = "testvcn"
}

resource "oci_core_internet_gateway" "test_internet_gateway" {
  compartment_id = var.OCI_COMPARTMENT_ID
  display_name   = "TestInternetGateway"
  vcn_id         = oci_core_vcn.test_vcn.id
}

resource "oci_core_default_route_table" "default_route_table" {
  manage_default_resource_id = oci_core_vcn.test_vcn.default_route_table_id
  display_name               = "DefaultRouteTable"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.test_internet_gateway.id
  }
}

resource "oci_core_subnet" "test_subnet" {
  availability_domain = data.oci_identity_availability_domain.ad.name
  cidr_block          = "10.1.20.0/24"
  display_name        = "TestSubnet"
  dns_label           = "testsubnet"
  security_list_ids   = [oci_core_vcn.test_vcn.default_security_list_id]
  compartment_id      = var.OCI_COMPARTMENT_ID
  vcn_id              = oci_core_vcn.test_vcn.id
  route_table_id      = oci_core_vcn.test_vcn.default_route_table_id
  dhcp_options_id     = oci_core_vcn.test_vcn.default_dhcp_options_id
}

resource "oci_core_instance" "test_instance" {
  count               = var.num_instances
  availability_domain = data.oci_identity_availability_domain.ad.name
  compartment_id      = var.OCI_COMPARTMENT_ID
  shape               = "VM.Standard.E3.Flex"
  freeform_tags       = { "Project" = "CNCF" }
  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_shape_config_memory_in_gbs
  }

  create_vnic_details {
    subnet_id                 = oci_core_subnet.test_subnet.id
    display_name              = "Primaryvnic"
    assign_public_ip          = true
    assign_private_dns_record = true
    hostname_label            = "exampleinstance${count.index}"
  }

  source_details {
    source_type = "image"
    source_id   = var.OCI_COMPUTE_IMAGE_ID
  }
  timeouts {
    create = "2m"
  }
}