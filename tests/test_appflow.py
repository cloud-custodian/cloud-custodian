# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
from c7n.tags import DEFAULT_TAG


class AppFlowTests(BaseTest):

    def test_appflow_tag(self):
        session_factory = self.replay_flight_data('test_appflow_tag')
        new_tag = {'lob': 'overhead'}
        p = self.load_policy(
            {
                'name': 'app-flow',
                'resource': 'app-flow',
                'filters': [{
                    'tag:lob': 'absent'
                }],
                'actions': [{
                    'type': 'tag',
                    'tags': new_tag
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        flow_name = resources[0].get('flowName')
        appflow = session_factory().client('appflow')
        call = appflow.describe_flow(flowName=flow_name)
        self.assertEqual(new_tag, call.get('tags'))

    def test_appflow_untag(self):
        session_factory = self.replay_flight_data('test_appflow_untag')
        p = self.load_policy(
            {
                'name': 'app-flow',
                'resource': 'app-flow',
                'filters': [{
                    'tag:lob': 'overhead'
                }],
                'actions': [{
                    'type': 'remove-tag',
                    'tags': ['lob']
                }],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        flow_name = resources[0].get('flowName')
        appflow = session_factory().client('appflow')
        call = appflow.describe_flow(flowName=flow_name)
        self.assertEqual({}, call.get('tags'))

    def test_appflow_mark_delete(self):
        session_factory = self.replay_flight_data('test_appflow_mark_delete')
        p = self.load_policy(
            {
                'name': 'app-flow',
                'resource': 'app-flow',
                'filters': [{
                    'tag:lob': 'absent'
                }],
                'actions': [{
                    'type': 'mark-for-op',
                    'op': 'delete',
                    'days': 1
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        flow_name = resources[0].get('flowName')
        appflow = session_factory().client('appflow')
        call = appflow.describe_flow(flowName=flow_name)
        self.assertIn(DEFAULT_TAG, call.get('tags').keys())

        p = self.load_policy(
            {
                'name': 'app-flow',
                'resource': 'app-flow',
                'filters': [{
                    'type': 'marked-for-op',
                    'op': 'delete',
                    'skew': 1
                }],
                'actions': [{
                    'type': 'delete',
                    'force': True
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))

        p = self.load_policy(
            {
                'name': 'app-flow',
                'resource': 'app-flow'
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(0, len(resources))
