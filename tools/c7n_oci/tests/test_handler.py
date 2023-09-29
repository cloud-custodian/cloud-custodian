# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import io
import json
import os
import types
from unittest.mock import patch

import oci
import yaml
from c7n_oci import handler
from oci_common import OciBaseTest
from pytest_terraform import terraform


class TestHandler(OciBaseTest):
    def _get_bucket_details(self, object_storage):
        namespace = object_storage["oci_objectstorage_bucket.test_bucket.namespace"]
        name = object_storage["oci_objectstorage_bucket.test_bucket.name"]
        compartment_id = object_storage["oci_objectstorage_bucket.test_bucket.compartment_id"]
        return namespace, name, compartment_id

    def _fetch_bucket_validation_data(self, session_factory, namespace_name, bucket_name):
        session = session_factory()
        client = session.client('oci.object_storage.ObjectStorageClient')
        resource = client.get_bucket(namespace_name, bucket_name)
        return oci.util.to_dict(resource.data)

    def _get_env_vars(self, test):
        policy = test.load_policy(
            {
                "name": "auto-tag-instance",
                "resource": "oci.bucket",
                "mode": {
                    "type": "oci-event",
                    "subnets": [
                        "ocid1.subnet.oc1.iad.aaaaaaaa5cgyc6mm6zcquu6w46cfqroppjzkrwyc7f3obflxh6rwnectzqvq"
                    ],
                    "events": ["createbucket"],
                },
                "actions": [{"type": "update", "freeform_tags": {"Source": "Custodian-function"}}],
            }
        )
        policy_yaml_string = yaml.dump({"policies": [policy.data]})
        return {
            'policy': policy_yaml_string,
            "execution-options": json.dumps({"region": os.environ.get("OCI_REGION")}),
        }

    @terraform("handler_resources", scope="class")
    def test_function_handler(self, test, handler_resources):
        namespace_name, bucket_name, compartment_id = self._get_bucket_details(handler_resources)
        session_factory = test.oci_session_factory()
        data = (
            '{"eventType": "com.oraclecloud.objectstorage.createbucket",\
                  "cloudEventsVersion": "0.1", "eventTypeVersion": "2.0", \
                    "source": "ObjectStorage", "data": \
                    {"compartmentId": "%s", \
                        "resourceName": "%s", "resourceId": "%s", \
                            "availabilityDomain": "IAD-AD-2", "freeformTags": {}}}'
            % (compartment_id, bucket_name, namespace_name)
        )
        data = data.encode('utf-8')
        data = io.BytesIO(data)
        ctx = types.SimpleNamespace()
        ctx.Config = lambda: os.environ
        with patch.dict(os.environ, self._get_env_vars(test)):
            handler.handler(ctx, data)
        resource = self._fetch_bucket_validation_data(session_factory, namespace_name, bucket_name)
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["freeform_tags"]["Source"], "Custodian-function")
