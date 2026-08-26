# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest
from pytest_terraform import terraform


class GCPSecretTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('gcp-secret-query')
        p = self.load_policy({
            'name': 'gcp-apikeys',
            'resource': 'gcp.secret'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 3)
        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/'
                                               'secrets/defectdojo_token')


@terraform('secret_set_labels')
def test_secret_set_labels(test, secret_set_labels):
    secret_name = secret_set_labels['google_secret_manager_secret.secret.name']
    factory = test.replay_flight_data('gcp-secret-set-label')
    policy = test.load_policy(
        {
            'name': 'gcp-secret-set-label',
            'resource': 'gcp.secret',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'value': secret_name,
            }],
            'actions': [
                {
                    'type': 'set-labels',
                    'labels': {'env': 'not-the-default'}
                }
            ]
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['labels']['env'] == 'default'

    client = policy.resource_manager.get_client()
    result = client.execute_query('get', {'name': secret_name})
    assert result['labels']['env'] == 'not-the-default'
