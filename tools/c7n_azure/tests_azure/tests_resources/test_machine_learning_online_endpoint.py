# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template, cassette_name


class MachineLearningOnlineEndpointTest(BaseTest):

    def test_machine_learning_online_endpoint_schema_validate(self):
        p = self.load_policy({
            'name': 'find-all-machine-learning-online-endpoints',
            'resource': 'azure.machine-learning-online-endpoint'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('machine-learning-online-endpoint.json')
    @cassette_name('machine-learning-online-endpoints')
    def test_machine_learning_online_endpoint_query(self):
        p = self.load_policy({
            'name': 'find-all-machine-learning-online-endpoints',
            'resource': 'azure.machine-learning-online-endpoint',
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('cctest-online-endpoint', resources[0]['name'])
        self.assertIn('/onlineEndpoints/', resources[0]['id'])

    @arm_template('machine-learning-online-endpoint.json')
    @cassette_name('machine-learning-online-endpoints')
    def test_machine_learning_online_endpoint_filter_provisioning_state(self):
        p = self.load_policy({
            'name': 'ml-online-endpoints-succeeded',
            'resource': 'azure.machine-learning-online-endpoint',
            'filters': [{
                'type': 'value',
                'key': 'properties.provisioningState',
                'value': 'Succeeded'
            }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('cctest-online-endpoint', resources[0]['name'])
