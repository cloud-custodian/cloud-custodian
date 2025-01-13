# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from unittest import mock
from .common import BaseTest


class ShieldTest(BaseTest):

    # most of the shield tests are embedded in other resources

    def test_shield_sync(self):
        # shield resources

        p = self.load_policy(
            {
                "name": "elb-sync",
                "resource": "elb",
                "actions": [{"type": "set-shield", "sync": True, "state": True}],
            }
        )

        client = mock.MagicMock()
        client.delete_protection = delete = mock.Mock()

        set_shield = p.resource_manager.actions[0]

        with mock.patch.object(p.resource_manager, "get_arns") as mock_get_arn:
            mock_get_arn.return_value = ["us-east-1:%s/lb" % i for i in map(str, range(5))]
            with mock.patch.object(
                p.resource_manager, "get_resource_manager"
            ) as mock_resource_manager:
                mock_resource_manager.return_value = mock_resource_manager
                mock_resource_manager.resources.return_value = map(str, range(5))
                protections = [
                    {"Id": i, "ResourceArn": "us-east-1:%s/lb" % i} for i in map(str, range(10))
                ]
                # One out of region
                protections.extend(
                    [{'Id': 42, 'ResourceArn': "us-east-2:42/lb"}]
                )

                # App elb also present for elb shield
                protections.extend(
                    [
                        {"Id": i, "ResourceArn": "us-east-1:%s/app/lb" % i}
                        for i in map(str, range(10, 15))
                    ]
                )
                # Networkload load balancers also present for elb shield
                protections.extend(
                    [
                        {"Id": i, "ResourceArn": "%s/net/lb" % i}
                        for i in map(str, range(10, 15))
                    ]
                )

                set_shield.clear_stale(client, protections)
                self.assertEqual(delete.call_count, 5)
                for i in range(5, 10):
                    self.assertTrue(
                        mock.call(ProtectionId=str(i)) in delete.call_args_list
                    )

    def test_tag_protection(self):
        session_factory = self.replay_flight_data("test_shield_tag_protection")
        p = self.load_policy(
            {
                "name": "tag-shield-protection",
                "resource": "shield-protection",
                "filters": [{"tag:Owner": "c7n"}],
                "actions": [{"type": "tag", "key": "c7n", "value": "test"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("shield")
        tags = client.list_tags_for_resource(ResourceARN=resources[0]["ResourceArn"])["Tags"]
        self.assertEqual(tags[1]["Value"], "test")

    def test_untag_protection(self):
        session_factory = self.replay_flight_data("test_shield_untag_protection")
        p = self.load_policy(
            {
                "name": "untag-shield-protection",
                "resource": "shield-protection",
                "filters": [{"tag:c7n": "test"}],
                "actions": [{"type": "remove-tag", "tags": ["c7n"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("shield")
        tags = client.list_tags_for_resource(ResourceARN=resources[0]["ResourceArn"])["Tags"]
        self.assertEqual(len(tags), 1)
        self.assertTrue(tags[0]["Key"] != "c7n")
