# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


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
