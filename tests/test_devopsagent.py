# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class DevOpsAgentSpaceTest(BaseTest):

    def test_devops_agent_space_augment(self):
        factory = self.replay_flight_data('test_devops_agent_space_augment')
        p = self.load_policy(
            {
                'name': 'devops-agent-space-augment',
                'resource': 'devops-agent-space',
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertGreater(len(resources), 0)
        self.assertIn('Tags', resources[0])
