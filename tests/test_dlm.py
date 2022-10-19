# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest


class DLMPolicyTest(BaseTest):

    def test_dlm_query(self):
        factory = self.replay_flight_data('test_dlm_query')
        p = self.load_policy({
            'name': 'dlm-query', 'resource': 'dlm-policy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        dlm = resources[0]
        self.maxDiff = None
        self.assertEqual(
            dlm['PolicyDetails'],
            {'ResourceTypes': ['VOLUME'],
             'Schedules': [{
                 'CreateRule': {
                     'Interval': 24,
                     'IntervalUnit': 'HOURS',
                     'Times': ['09:00']},
                 'Name': 'Default Schedule',
                 'RetainRule': {'Count': 5}}],
             'TargetTags': [{'Key': 'App', 'Value': 'Zebra'}]})

    def test_dlm_tag(self):
        factory = self.replay_flight_data('test_dlm_tag')
        p = self.load_policy(
            {
                'name': 'tag-dlm',
                'resource': 'dlm-policy',
                'filters': [
                    {'tag:bar': 'absent'}
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {
                            'bar': 'baz'
                        }
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                'name': 'tag-dlm',
                'resource': 'dlm-policy',
                'filters': [
                    {'tag:bar': 'present'}
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_dlm_remove_tag(self):
        factory = self.replay_flight_data('test_dlm_remove_tag')
        p = self.load_policy(
            {
                'name': 'tag-dlm',
                'resource': 'dlm-policy',
                'filters': [
                    {'tag:foo': 'present'}
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': [
                            'foo'
                        ]
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                'name': 'tag-dlm',
                'resource': 'dlm-policy',
                'filters': [
                    {'tag:foo': 'present'}
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)
