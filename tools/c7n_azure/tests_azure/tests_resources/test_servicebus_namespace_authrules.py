# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class ServiceBusNamespaceAuthRulesTest(BaseTest):
    def test_azure_servicebus_namespace_authrules_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-servicebus-namespace-authrules-schema-validate',
            'resource': 'azure.servicebus-namespace-authrules'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-azure-servicebus-namespace-authrules',
            'resource': 'azure.servicebus-namespace-authrules',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'c7nfail-sbnamespace-arule'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
