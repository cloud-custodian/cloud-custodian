# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class RecoveryServicesTest(BaseTest):

    def test_recovery_services_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-recovery-services',
                'resource': 'azure.recovery-services'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('recoveryservices.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-recovery-services',
            'resource': 'azure.recovery-services',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cfbukqrkhntars655e53akvrc4k'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
