# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import io
import json
import os
import types
from unittest.mock import Mock, patch

import oci
import pytest
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
        mock = Mock()
        with patch('docker.from_env') as mock_from_env:
            mock_docker_client = Mock(spec_set=['version', 'login'])
            mock_from_env.return_value = mock_docker_client
            mock_docker_client.version.return_value = mock
            mock_docker_client.login.return_value = mock
            with patch.dict(os.environ, self._get_env_vars(test)):
                handler.handler(ctx, data)
        resource = self._fetch_bucket_validation_data(session_factory, namespace_name, bucket_name)
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["freeform_tags"]["Source"], "Custodian-function")

    def test_invalid_json_payload(self):
        data = ''
        data = data.encode('utf-8')
        data = io.BytesIO(data)
        ctx = types.SimpleNamespace()
        ctx.Config = lambda: os.environ

        with pytest.raises(ValueError) as error:
            with patch.dict(os.environ):
                handler.handler(ctx, data)

        assert str(error.value) == "Expecting value: line 1 column 1 (char 0)"

    def test_no_policy_found(self, caplog):
        data = '{"eventType": "com.oraclecloud.objectstorage.createbucket",\
                  "cloudEventsVersion": "0.1", "eventTypeVersion": "2.0", \
                    "source": "ObjectStorage", "data": \
                    {"compartmentId": "ocid1.compartment.oc1..<unique_ID>", \
                        "resourceName": "test", "resourceId": "abc", \
                            "availabilityDomain": "IAD-AD-2", "freeformTags": {}}}'
        data = data.encode('utf-8')
        data = io.BytesIO(data)
        ctx = types.SimpleNamespace()
        ctx.Config = lambda: os.environ
        handler.handler(ctx, data)
        logs = caplog.records
        error_logs = [log for log in logs if log.levelname == "ERROR"]

        assert error_logs[0].msg == 'No policy found in function configuration'

    def test_invalid_policy_config(self, caplog):
        data = '{"eventType": "com.oraclecloud.objectstorage.createbucket",\
                  "cloudEventsVersion": "0.1", "eventTypeVersion": "2.0", \
                    "source": "ObjectStorage", "data": \
                    {"compartmentId": "ocid1.compartment.oc1..<unique_ID>", \
                        "resourceName": "test", "resourceId": "abc", \
                            "availabilityDomain": "IAD-AD-2", "freeformTags": {}}}'
        data = data.encode('utf-8')
        data = io.BytesIO(data)
        ctx = types.SimpleNamespace()
        ctx.Config = lambda: os.environ

        with patch.dict(os.environ, {'policy': yaml.dump({"policies": []})}):
            handler.handler(ctx, data)

        logs = caplog.records
        error_logs = [log for log in logs if log.levelname == "ERROR"]

        assert error_logs[0].msg == 'Invalid policy config'
