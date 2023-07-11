# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register("armor-policy")
class SecurityPolicy(QueryResourceManager):
    """Cloud Armor Policy

    Cloud Armor is GCP's WAF technology providing DDOS and Layer 7
    (SQLi, XSS) rules based protection for load balancers and public
    ip VMs.

    GC resource: https://cloud.google.com/compute/docs/reference/rest/v1/securityPolicies

    """

    class resource_type(TypeInfo):
        service = "compute"
        version = "v1"
        component = "securityPolicies"
        scope_key = "project"
        name = id = "name"
        scope_template = "{}"
        permissions = ("compute.securityPolicies.list",)
        default_report_fields = ["name", "description", "creationTimestamp"]
        asset_type = "compute.googleapis.com/SecurityPolicy"
        urn_id_path = "name"
        urn_component = "securityPolicy"
