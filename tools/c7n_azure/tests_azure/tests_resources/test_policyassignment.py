# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class PolicyAssignmentTest(BaseTest):

    def test_policy_assignment_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-policy-assignment',
                'resource': 'azure.policyassignments'
            }, validate=True)
            self.assertTrue(p)

    # run ./templates/provision.sh policyassignment to deploy required resource.
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.policyassignments',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestpolicy'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
