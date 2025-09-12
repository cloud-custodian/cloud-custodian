# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class AppServiceEnvironmentTest(BaseTest):

    def test_validate_ase_schema(self):
        with self.sign_out_patch():
            p = self.load_policy({
                "name": "test-azure-ase",
                "resource": "azure.app-service-environment"
            }, validate=True)

            self.assertTrue(p)

    def test_find_ase_in_pending_state(self):
        p = self.load_policy({
            "name": "test-azure-ase",
            "resource": "azure.app-service-environment",
            "filters": [
                {"type": "value",
                 "key": "properties.provisioningState",
                 "value": "InProgress"}
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["name"], "example-ase")
