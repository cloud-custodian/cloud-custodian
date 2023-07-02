# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from enum import Enum

"""
Oracle Cloud Infrastructure Authentication
"""
ENV_FINGERPRINT = "OCI_FINGERPRINT"
ENV_KEY_FILE = "OCI_KEY_FILE"
ENV_REGION = "OCI_REGION"
ENV_TENANCY = "OCI_TENANCY"
ENV_USER = "OCI_USER"
COMPARTMENT_IDS = "OCI_COMPARTMENTS"
DEFAULT_PROFILE = "DEFAULT"
STORAGE_NAMESPACE = "namespace_name"


class Service(Enum):
    CORE = "oci.core"
    MONITORING = "oci.monitoring"
    DNS = "oci.dns"
    IDENTITY = "oci.identity"
    OBJECT_STORAGE = "oci.object_storage"


class Client(Enum):
    COMPUTE = "ComputeClient"
    MONITORING = "MonitoringClient"
    DNS = "DnsClient"
    IDENTITY = "IdentityClient"
    OBJECT_STORAGE = "ObjectStorageClient"
    VIRTUAL_NETWORK = "VirtualNetworkClient"
