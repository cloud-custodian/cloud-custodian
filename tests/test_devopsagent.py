# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class DevOpsAgentSpaceTest(BaseTest):

    def test_devops_agent_space_augment(self):
        session_factory = self.record_flight_data('test_devops_agent_space_augment')

        p = self.load_policy(
            {
                'name': 'devops-agent-space-augment',
                'resource': 'devops-agent-space',
                'filters': [{'tag:agentName': 'testAgent'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['Tags'],
            [
                {'Key': 'agentName', 'Value': 'testAgent'},
                {'Key': 'agentAssociation', 'Value': 'pretendService'},
            ],
        )
