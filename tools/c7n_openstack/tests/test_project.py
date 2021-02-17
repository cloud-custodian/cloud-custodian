# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_openstack import OpenStackTest


class ProjectTest(OpenStackTest):

    def test_project_query(self):
        factory = self.replay_flight_data()
        p = self.load_policy({
            'name': 'all-projects',
            'resource': 'openstack.project'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_project_filter_by_name(self):
        factory = self.replay_flight_data()
        policy = {
            'name': 'project-demo',
            'resource': 'openstack.project',
            'filters': [
                {
                    "type": "value",
                    "key": "name",
                    "value": "demo",
                },
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].name, "demo")
