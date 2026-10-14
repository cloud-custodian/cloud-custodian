# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from gcp_common import BaseTest
from pytest_terraform import terraform


class FunctionTest(BaseTest):

    def test_delete(self):
        factory = self.replay_flight_data(
            'function-delete', project_id='cloud-custodian')
        p = self.load_policy({
            'name': 'func-del',
            'resource': 'gcp.function',
            'filters': [
                {'httpsTrigger': 'present'},
                {'entryPoint': 'hello_http'}],
            'actions': ['delete']}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['status'], 'ACTIVE')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:cloudfunctions:us-central1:cloud-custodian:function/hello_http'
            ],
        )

        client = p.resource_manager.get_client()
        func = client.execute_query(
            'get', {'name': resources[0]['name']})
        self.maxDiff = None
        self.assertEqual(func['status'], 'DELETE_IN_PROGRESS')
        self.assertEqual(
            p.resource_manager.get_urns([func]),
            [
                'gcp:cloudfunctions:us-central1:cloud-custodian:function/hello_http'
            ],
        )


@terraform('function_labels')
def test_function_labels(test, function_labels):
    function_name = function_labels['google_cloudfunctions_function.default.id']
    factory = test.replay_flight_data('function-label')
    policy = test.load_policy(
        {
            'name': 'function-label',
            'resource': 'gcp.function',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'value': function_name,
            }],
            'actions': [{
                'type': 'set-labels',
                'labels': {'env': 'not-the-default'},
            }],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['labels']['env'] == 'default'

    client = policy.resource_manager.get_client()

    # Wait for the function to finish starting up and get the label applied.
    for _ in range(30):
        result = client.execute_query('get', {'name': function_name})
        if result['labels']['env'] == 'not-the-default':
            break
        if test.recording:
            time.sleep(10)
    else:
        raise Exception("Timed out waiting for the label to change.")

    if test.recording:
        # Giving extra time helps the automatic deletion during teardown not to break.
        time.sleep(30)
