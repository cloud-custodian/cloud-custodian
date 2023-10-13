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

    def test_azure_defender_contacts(self):
        p = self.load_policy({
            'name': 'test-security-contacts',
            'resource': 'azure.defender-contacts'
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('azurebilling@epmcseclab.com', resources[0]['properties']['email'])

    def test_azure_defender_contacts_validate_schemas(self):
        p = self.load_policy({
            'name': 'test-security-contacts-schema-validate',
            'resource': 'azure.defender-contacts',
        }, validate=True)
        self.assertTrue(p)

    def test_azure_defender_jit_policies_query(self):
        p = self.load_policy({
            'name': 'test-security-jit-policies',
            'resource': 'azure.defender-jit-policies',
        })
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'VVvm1')

    def test_azure_defender_jit_policies_filter(self):
        p = self.load_policy({
            'name': 'test-security-jit-policies-filter',
            'resource': 'azure.defender-jit-policies',
            'filters': [{
                'type': 'defender-jit-policies-filter',
                'key': 'properties.virtualMachines[].ports[].number',
                'op': 'eq',
                'value': 22
            }, {
                'type': 'defender-jit-policies-filter',
                'key': 'properties.virtualMachines[].id',
                'op': 'regex',
                'value': r'\/.+\/virtualMachines\/.+'}]})
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'VVvm1')
