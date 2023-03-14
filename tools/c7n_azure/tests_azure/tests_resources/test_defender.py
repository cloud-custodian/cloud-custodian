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
