# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

ResourceMap = {
    "oci.bucket": "c7n_oci.resources.object_storage.Bucket",
    "oci.instance": "c7n_oci.resources.compute.Instance",
    "oci.vcn": "c7n_oci.resources.virtual_network.Vcn",
    "oci.subnet": "c7n_oci.resources.virtual_network.Subnet",
    "oci.cross_connect": "c7n_oci.resources.virtual_network.Cross_connect",
    "oci.zone": "c7n_oci.resources.dns.Zone",
    "oci.compartment": "c7n_oci.resources.identity.Compartment",
    "oci.group": "c7n_oci.resources.identity.Group",
    "oci.user": "c7n_oci.resources.identity.User",
}
