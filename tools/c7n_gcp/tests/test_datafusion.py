# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from gcp_common import BaseTest


class DatafusionInstanceTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('gcp-datafusion-instance-query')
        p = self.load_policy({
            'name': 'gcp-datafusion',
            'resource': 'gcp.datafusion-instance'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/'
                                               'locations/us-central1/'
                                               'instances/instance-311-green')

        assert p.resource_manager.get_urns(resources) == [
            "gcp:datafusion:us-central1:cloud-custodian:instances/instance-311-green"
        ]
