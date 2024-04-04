# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import re
import time

import oci

from c7n.schema import generate
from c7n.testing import C7N_FUNCTIONAL

FILTERED_FIELDS = ["metadata"]


class OciBaseTest:
    custodian_schema = generate()

    def get_defined_tag(self, test_type):
        return {
            "cloud-custodian-test": {
                "mark-for-resize": "true" if test_type == "add_tag" else "false"
            }
        }

    def get_defined_tag_value(self, tag_details):
        if tag_details.get("cloud-custodian-test"):
            return tag_details.get("cloud-custodian-test").get("mark-for-resize")

    def get_defined_tag_key(self):
        return 'defined_tags."cloud-custodian-test"."mark-for-resize"'

    def wait(self, duration=15):
        if C7N_FUNCTIONAL:
            time.sleep(duration)

    def fetch_validation_data(self, resource_manager, operation, resource_id):
        func = getattr(resource_manager.get_client(), operation)
        resources = func(resource_id)
        if isinstance(resources, list):
            return [oci.util.to_dict(resource.data) for resource in resources]
        else:
            return oci.util.to_dict(resources.data)


# common functions
def replace_ocid(data):
    return re.sub(r'\.oc1\..*?"', '.oc1..<unique_ID>"', data)


def replace_email(data):
    return re.sub(r'"[^"]+@oracle\.com"', '"user@example.com"', data)


def replace_namespace(data):
    return re.sub(r'"namespace"\s*:\s*"[^"]*"', r'"namespace": "<namespace>"', data)


def sanitize_response_body(data):
    if isinstance(data, list):
        for resource in data:
            for field in FILTERED_FIELDS:
                if field in resource:
                    del resource[field]
    return data
