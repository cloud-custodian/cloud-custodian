import os
import sys
from c7n.vendored.distutils.util import strtobool

import oci
import pytest
from pytest_terraform import terraform

from c7n.testing import C7N_FUNCTIONAL
from oci_common import OciBaseTest

OCI_INSTANCE_PRINCIPAL = strtobool(os.environ.get('OCI_INSTANCE_PRINCIPAL', 'no'))
skip_test = True
if (OCI_INSTANCE_PRINCIPAL and C7N_FUNCTIONAL) or not (OCI_INSTANCE_PRINCIPAL or C7N_FUNCTIONAL):
    skip_test = False


@pytest.mark.skipif(
    skip_test or sys.platform == "win32",
    reason="This test can only run on a configured OCI Instance",
)
class TestInstancePrincipalAuth(OciBaseTest):
    def _get_bucket_details(self, object_storage):
        namespace = object_storage["oci_objectstorage_bucket.ip_test_bucket.namespace"]
        name = object_storage["oci_objectstorage_bucket.ip_test_bucket.name"]
        return namespace, name

    def _fetch_bucket_validation_data(self, resource_manager, namespace_name, bucket_name):
        client = resource_manager.get_client()
        resource = client.get_bucket(namespace_name, bucket_name)
        return oci.util.to_dict(resource.data)

    @terraform("ip_auth", scope="class")
    def test_list_bucket(self, test, ip_auth, with_or_without_compartment):
        os.environ['OCI_CLI_AUTH'] = 'instance_principal'
        namespace_name, bucket_name = self._get_bucket_details(ip_auth)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "list-bucket",
                "resource": "oci.bucket",
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        os.environ['OCI_CLI_AUTH'] = 'None'
