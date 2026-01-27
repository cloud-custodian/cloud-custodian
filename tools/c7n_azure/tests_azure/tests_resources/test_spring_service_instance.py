# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class SpringServiceInstanceTest(BaseTest):
    def test_azure_springserviceinstance_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-springserviceinstance-schema-validate',
            'resource': 'azure.spring-service-instance'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-azure-springserviceinstance',
            'resource': 'azure.spring-service-instance',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'test-spring-service2'}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
