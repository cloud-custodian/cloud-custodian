# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class GlobalAcceleratorTest(BaseTest):

    def test_globalaccelerator_tag_untag(self):
        session_factory = self.replay_flight_data('test_globalaccelerator_tag_untag')
        tag = {'env': 'dev'}
        p = self.load_policy(
            {
                'name': 'globalaccelerator-tag-untag',
                'resource': 'globalaccelerator',
                'filters': [{
                    'tag:owner': 'policy'
                }],
                'actions': [{
                    'type': 'tag',
                    'tags': tag
                },
                {
                    'type': 'remove-tag',
                    'tags': ['owner']
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        client = session_factory(region="us-west-2").client("globalaccelerator")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["AcceleratorArn"])["Tags"]
        self.assertEqual(1, len(tags))
        new_tag = {}
        new_tag[tags[0]['Key']] = tags[0]['Value']
        self.assertEqual(tag, new_tag)

    def test_globalaccelerator_mark_for_op(self):
        session_factory = self.replay_flight_data("test_globalaccelerator_mark_for_op")
        p = self.load_policy(
            {
                "name": "globalaccelerator-mark",
                "resource": "globalaccelerator",
                "filters": [
                    {'tag:owner': 'policy'},
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "notify",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "globalaccelerator-marked",
                "resource": "globalaccelerator",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "notify",
                        "skew": 3,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert resources[0]['Name'] == 'test-custodian'
