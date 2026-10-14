# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

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
        labels = True
        labels_op = "setLabels"
        scope_template = "{}"
        permissions = ("compute.securityPolicies.list",)
        default_report_fields = ["name", "description", "creationTimestamp"]
        asset_type = "compute.googleapis.com/SecurityPolicy"
        urn_id_path = "name"
        urn_component = "securityPolicy"

        @staticmethod
        def parse_params(resc_name):
            """Takes resourceName (from a log) or selfLink (from a resource) and parses from it the
            parameters needed to make a request (project and policy)"""
            exp = r".*projects\/(.*)\/global/securityPolicies\/(.*)"
            return re.match(exp, resc_name).groups()

        @classmethod
        def get(cls, client, resource_info):
            project, policy = cls.parse_params(resource_info['resourceName'])
            return client.execute_command(
                "get",
                {
                    "project": project,
                    "securityPolicy": policy,
                },
            )

        @classmethod
        def get_label_params(cls, resource, all_labels):
            project, policy = cls.parse_params(resource['selfLink'])
            return {
                "project": project,
                "resource": policy,
                "body": {
                    "labels": all_labels,
                    "labelFingerprint": resource["labelFingerprint"],
                },
            }

        @classmethod
        def refresh(cls, client, resource):
            """This method is used to refresh labelFingerprint when a label action fails because the
            fingerprint was stale."""
            return cls.get(client, {'resourceName': resource['selfLink']})
