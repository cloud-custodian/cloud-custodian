# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from gcp_common import BaseTest


class PatchDeploymentTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('gcp-patch-deployment-query')
        p = self.load_policy({
            'name': 'gcp-patch-deployment',
            'resource': 'gcp.patch-deployment'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/patchDeployments/test')

        assert p.resource_manager.get_urns(resources) == [
            "gcp:osconfig::cloud-custodian:patchDeployment/test"
        ]
