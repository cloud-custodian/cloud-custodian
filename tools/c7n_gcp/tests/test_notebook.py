# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from gcp_common import BaseTest


class NotebookInstanceTest(BaseTest):

    def test_notebook_instance_query(self):
        project_id = 'gcp-lab-custodian'
        factory = self.replay_flight_data('test_notebook_instance_list_query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'notebook-instance-query',
             'resource': 'gcp.notebook'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/'
                                               'locations/us-central1-a/instances/instancetest')
        assert p.resource_manager.get_urns(resources) == [
            "gcp:notebooks:us-central1-a:gcp-lab-custodian:instances/instancetest"
        ]
