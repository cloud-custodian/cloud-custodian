# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template


class MachineLearningModelVersionTest(BaseTest):

    def test_machine_learning_model_version_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'find-all-machine-learning-model-versions',
                'resource': 'azure.machine-learning-model-version'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('machine-learning-model-version.json')
    def test_machine_learning_model_version_query(self):
        p = self.load_policy({
            'name': 'find-all-machine-learning-model-versions',
            'resource': 'azure.machine-learning-model-version',
        })
        resources = p.run()
        self.assertEqual(2, len(resources))
        self.assertTrue(all('/models/cctest-model/versions/' in r['id'] for r in resources))
        self.assertTrue(all('c7n:parent-id' in r for r in resources))

    @arm_template('machine-learning-model-version.json')
    def test_machine_learning_model_version_filter_archived(self):
        p = self.load_policy({
            'name': 'find-archived-model-versions',
            'resource': 'azure.machine-learning-model-version',
            'filters': [{
                'type': 'value',
                'key': 'properties.isArchived',
                'value': True
            }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('2', resources[0]['name'])
