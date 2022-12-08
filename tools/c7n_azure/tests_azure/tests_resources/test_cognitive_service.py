# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class CognitiveServiceTest(BaseTest):
    def setUp(self):
        super(CognitiveServiceTest, self).setUp()

    def test_cognitive_service_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-cognitive-service',
                'resource': 'azure.cognitiveservice'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cognitive-service.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-cog-serv',
            'resource': 'azure.cognitiveservice',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'cctest-cog-serv'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
