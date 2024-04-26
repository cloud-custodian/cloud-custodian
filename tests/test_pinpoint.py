# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class PinpointApp(BaseTest):

    def test_pinpoint_app_tag(self):
        session_factory = self.replay_flight_data('test_pinpoint_app_tag')
        p = self.load_policy(
            {
                'name': 'test-pinpoint-app-tag',
                'resource': 'pinpoint-app',
                'filters': [
                    {
                        'tag:foo': 'absent',
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('pinpoint')
        tags = client.list_tags_for_resource(ResourceArn=resources[0]['Arn'])['TagsModel']['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {'foo': 'bar'})

    def test_pinpoint_app_remove_tag(self):
        session_factory = self.replay_flight_data('test_pinpoint_app_remove_tag')
        p = self.load_policy(
            {
                'name': 'test-pinpoint-app-remove-tag',
                'resource': 'pinpoint-app',
                'filters': [
                    {
                        'tag:foo': 'present',
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': ['foo']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('pinpoint')
        tags = client.list_tags_for_resource(ResourceArn=resources[0]['Arn'])['TagsModel']['tags']
        self.assertEqual(len(tags), 0)
