# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class FunctionTest(BaseTest):

    def test_function_filter_iam_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('function-filter-iam', project_id=project_id)
        p = self.load_policy({
            'name': 'function-filter-iam',
            'resource': 'gcp.function',
            'filters': [{
                'type': 'iam-policy',
                'doc': {
                    'key': "bindings[?(role=='roles\\editor' || role=='roles\\owner')]",
                    'op': 'ne',
                    'value': []
                }
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('projects/cloud-custodian/locations/us-central1/functions/function-4',
                         resources[0]['name'])
