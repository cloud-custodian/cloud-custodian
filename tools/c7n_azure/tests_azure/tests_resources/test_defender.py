# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class DefenderTest(BaseTest):
    def test_azure_defender_pricing(self):
        p = self.load_policy(
            {
                "name": "test-azure-defender-pricing",
                "resource": "azure.defender-pricing",
                "filters": [
                    {"name": "KeyVaults"},
                ],
            }
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_azure_defender_setting(self):
        p = self.load_policy(
            {
                "name": "test-azure-defender-setting",
                "resource": "azure.defender-setting",
                "filters": [
                    {"name": "MCAS"},
                    {"kind": "DataExportSettings"},
                    {"properties.enabled": True},
                ],
            }
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_azure_defender_autoprovisioning(self):
        p = self.load_policy(
            {
                "name": "test-azure-defender-autoprovisioning",
                "resource": "azure.defender-autoprovisioning",
                "filters": [
                    {"name": "default"},
                    {"properties.autoProvision": "On"},
                ],
            }
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_azure_defender_assessments(self):
        p = self.load_policy({
            'name': 'test-security-assessments',
            'resource': 'azure.defender-assessment',
            'filters': [{
                'type': 'value',
                'key': 'properties.status.code',
                'op': 'eq',
                'value': 'Healthy'}]})
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], '2a548cf9-6de3-491e-b24a-cf277fe36d4d')
