# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class ServiceFabricTest(BaseTest):
    def test_azure_fabric_managed_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-service-fabric-cluster-managed',
            'resource': 'azure.service-fabric-cluster-managed'
        }, validate=True)
        self.assertTrue(p)

    def test_azure_fabric_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-service-fabric-cluster',
                'resource': 'azure.service-fabric-cluster'
            }, validate=True)
            self.assertTrue(p)

    def test_find_managed_by_name(self):
        p = self.load_policy({
            'name': 'test-service-fabric-cluster',
            'resource': 'azure.service-fabric-cluster-managed',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccfabric*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
