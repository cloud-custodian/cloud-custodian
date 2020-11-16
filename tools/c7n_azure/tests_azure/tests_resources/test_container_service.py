# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest
import pytest


# Deployment requires Graph permissions
@pytest.mark.skiplive
class ContainerServiceTest(BaseTest):
    def setUp(self):
        super(ContainerServiceTest, self).setUp()

    def test_container_service_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-container-service',
                'resource': 'azure.containerservice'
            }, validate=True)
            self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-containerservice',
            'resource': 'azure.containerservice',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestacs'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
