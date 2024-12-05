# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class ServiceBusNamespaceNetworkrulesTest(BaseTest):
    def test_azure_servicebus_namespace_networkrules_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-servicebus-namespace-networkrules-schema-validate',
            'resource': 'azure.servicebus-namespace-networkrules'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-azure-servicebus-namespace-networkrules',
            'resource': 'azure.servicebus-namespace-networkrules',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'default'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
