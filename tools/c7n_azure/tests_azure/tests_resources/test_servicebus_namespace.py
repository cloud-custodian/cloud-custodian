# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class ServiceBusNamespaceTest(BaseTest):
    def test_azure_servicebus_namespace_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-servicebus-namespace-schema-validate',
            'resource': 'azure.servicebus-namespace'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-azure-servicebus-namespace',
            'resource': 'azure.servicebus-namespace',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'cctestservicebusnamespacejv67tef5di5hy'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
