# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class SourceRepoTest(BaseTest):

    def test_sourcerepo_query(self):
        project_id = 'cloud-custodian'
        repo_name = 'projects/cloud-custodian/repos/test-repo'
        session_factory = self.replay_flight_data(
            'sourcerepo-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-sourcerepo-query',
             'resource': 'gcp.sourcerepo'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], repo_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                "gcp:sourcerepo::cloud-custodian:repo/test-repo",
            ],
        )
