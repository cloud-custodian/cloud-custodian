# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

from .common import BaseTest, functional
from c7n.resources.aws import shape_validate
from c7n.utils import yaml_load


class TestSNS(BaseTest):

    @functional
    def test_sns_remove_matched(self):
        session_factory = self.replay_flight_data("test_sns_remove_matched")
        client = session_factory().client("sns")
        name = "test-sns-remove-matched"
        topic_arn = client.create_topic(Name=name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "SpecificAllow",
                            "Effect": "Allow",
                            "Principal": {"AWS": "arn:aws:iam::644160558196:root"},
                            "Action": ["SNS:Subscribe"],
                            "Resource": topic_arn,
                        },
                        {
                            "Sid": "Public",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:GetTopicAttributes"],
                            "Resource": topic_arn,
                        },
                    ],
                }
            ),
        )

        p = self.load_policy(
            {
                "name": "sns-rm-matched",
                "resource": "sns",
                "filters": [
                    {"TopicArn": topic_arn},
                    {"type": "cross-account", "whitelist": ["644160558196"]},
                ],
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()

        self.assertEqual([r["TopicArn"] for r in resources], [topic_arn])

        data = json.loads(
            client.get_topic_attributes(TopicArn=resources[0]["TopicArn"])[
                "Attributes"
            ][
                "Policy"
            ]
        )
        self.assertEqual(
            [s["Sid"] for s in data.get("Statement", ())], ["SpecificAllow"]
        )

    @functional
    def test_sns_remove_named(self):
        session_factory = self.replay_flight_data("test_sns_remove_named")
        client = session_factory().client("sns")
        name = "test-sns-remove-named"
        topic_arn = client.create_topic(Name=name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "SpecificAllow",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:Subscribe"],
                            "Resource": topic_arn,
                        },
                        {
                            "Sid": "RemoveMe",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:GetTopicAttributes"],
                            "Resource": topic_arn,
                        },
                    ],
                }
            ),
        )

        p = self.load_policy(
            {
                "name": "sns-rm-named",
                "resource": "sns",
                "filters": [{"TopicArn": topic_arn}],
                "actions": [
                    {"type": "remove-statements", "statement_ids": ["RemoveMe"]}
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        data = json.loads(
            client.get_topic_attributes(TopicArn=resources[0]["TopicArn"])[
                "Attributes"
            ][
                "Policy"
            ]
        )
        self.assertTrue("RemoveMe" not in [s["Sid"] for s in data.get("Statement", ())])

    @functional
    def test_sns_modify_replace_policy(self):
        session_factory = self.replay_flight_data("test_sns_modify_replace_policy")
        client = session_factory().client("sns")
        name = "test_sns_modify_replace_policy"
        topic_arn = client.create_topic(Name=name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "SpecificAllow",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:Subscribe"],
                            "Resource": topic_arn,
                        }
                    ],
                }
            ),
        )

        p = self.load_policy(
            {
                "name": "sns-modify-replace-policy",
                "resource": "sns",
                "filters": [{"TopicArn": topic_arn}],
                "actions": [
                    {
                        "type": "modify-policy",
                        "add-statements": [
                            {
                                "Sid": "ReplaceWithMe",
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": ["SNS:GetTopicAttributes"],
                                "Resource": topic_arn,
                            }
                        ],
                        "remove-statements": "*",
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        data = json.loads(
            client.get_topic_attributes(TopicArn=resources[0]["TopicArn"])[
                "Attributes"
            ][
                "Policy"
            ]
        )
        self.assertTrue(
            "ReplaceWithMe" in [s["Sid"] for s in data.get("Statement", ())]
        )

    @functional
    def test_sns_account_id_template(self):
        session_factory = self.replay_flight_data("test_sns_account_id_template")
        client = session_factory().client("sns")
        name = "test_sns_account_id_template"
        topic_arn = client.create_topic(Name=name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "SpecificAllow",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:Subscribe"],
                            "Resource": topic_arn,
                        }
                    ],
                }
            ),
        )

        p = self.load_policy(
            {
                "name": "sns-modify-replace-policy",
                "resource": "sns",
                "filters": [{"TopicArn": topic_arn}],
                "actions": [
                    {
                        "type": "modify-policy",
                        "add-statements": [
                            {
                                "Sid": "__default_statement_ID_{account_id}",
                                "Effect": "Allow",
                                "Principal": {"Service": "s3.amazonaws.com"},
                                "Action": "SNS:Publish",
                                "Resource": topic_arn,
                                "Condition": {
                                    "StringEquals": {
                                        "AWS:SourceAccount": "{account_id}"
                                    },
                                    "ArnLike": {"aws:SourceArn": "arn:aws:s3:*:*:*"},
                                },
                            }
                        ],
                        "remove-statements": "*",
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        data = json.loads(
            client.get_topic_attributes(TopicArn=resources[0]["TopicArn"])[
                "Attributes"
            ][
                "Policy"
            ]
        )
        self.assertTrue(
            "__default_statement_ID_" +
            self.account_id in [s["Sid"] for s in data.get("Statement", ())]
        )

    @functional
    def test_sns_modify_remove_policy(self):
        session_factory = self.replay_flight_data("test_sns_modify_remove_policy")
        client = session_factory().client("sns")
        name = "test_sns_modify_remove_policy"
        topic_arn = client.create_topic(Name=name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "SpecificAllow",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:Subscribe"],
                            "Resource": topic_arn,
                        },
                        {
                            "Sid": "RemoveMe",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:GetTopicAttributes"],
                            "Resource": topic_arn,
                        },
                    ],
                }
            ),
        )

        p = self.load_policy(
            {
                "name": "sns-modify-remove-policy",
                "resource": "sns",
                "filters": [{"TopicArn": topic_arn}],
                "actions": [
                    {
                        "type": "modify-policy",
                        "add-statements": [],
                        "remove-statements": ["RemoveMe"],
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        data = json.loads(
            client.get_topic_attributes(TopicArn=resources[0]["TopicArn"])[
                "Attributes"
            ][
                "Policy"
            ]
        )
        self.assertTrue("RemoveMe" not in [s["Sid"] for s in data.get("Statement", ())])

    @functional
    def test_sns_modify_add_policy(self):
        session_factory = self.replay_flight_data("test_sns_modify_add_policy")
        client = session_factory().client("sns")
        name = "test_sns_modify_add_policy"
        topic_arn = client.create_topic(Name=name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "SpecificAllow",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:Subscribe"],
                            "Resource": topic_arn,
                        }
                    ],
                }
            ),
        )

        p = self.load_policy(
            {
                "name": "sns-modify-add-policy",
                "resource": "sns",
                "filters": [{"TopicArn": topic_arn}],
                "actions": [
                    {
                        "type": "modify-policy",
                        "add-statements": [
                            {
                                "Sid": "AddMe",
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": ["SNS:GetTopicAttributes"],
                                "Resource": topic_arn,
                            }
                        ],
                        "remove-statements": [],
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        data = json.loads(
            client.get_topic_attributes(TopicArn=resources[0]["TopicArn"])[
                "Attributes"
            ][
                "Policy"
            ]
        )
        self.assertTrue("AddMe" in [s["Sid"] for s in data.get("Statement", ())])

    @functional
    def test_sns_modify_add_and_remove_policy(self):
        session_factory = self.replay_flight_data(
            "test_sns_modify_add_and_remove_policy"
        )
        client = session_factory().client("sns")
        name = "test_sns_modify_add_and_remove_policy"
        topic_arn = client.create_topic(Name=name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "SpecificAllow",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:Subscribe"],
                            "Resource": topic_arn,
                        },
                        {
                            "Sid": "RemoveMe",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:GetTopicAttributes"],
                            "Resource": topic_arn,
                        },
                    ],
                }
            ),
        )

        p = self.load_policy(
            {
                "name": "sns-modify-add-and-remove-policy",
                "resource": "sns",
                "filters": [{"TopicArn": topic_arn}],
                "actions": [
                    {
                        "type": "modify-policy",
                        "add-statements": [
                            {
                                "Sid": "AddMe",
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": ["SNS:GetTopicAttributes"],
                                "Resource": topic_arn,
                            }
                        ],
                        "remove-statements": ["RemoveMe"],
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        data = json.loads(
            client.get_topic_attributes(TopicArn=resources[0]["TopicArn"])[
                "Attributes"
            ][
                "Policy"
            ]
        )
        statement_ids = {s["Sid"] for s in data.get("Statement", ())}
        self.assertTrue("AddMe" in statement_ids)
        self.assertTrue("RemoveMe" not in statement_ids)
        self.assertTrue("SpecificAllow" in statement_ids)

    def test_sns_modify_add_policy_without_sid(self):
        session_factory = self.replay_flight_data("test_sns_modify_add_policy_without_sid")
        client = session_factory().client("sns")
        name = "c7n-test-rbp-no-sid"
        topic_arn = client.create_topic(Name=name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["SNS:Subscribe"],
                            "Resource": topic_arn,
                        }
                    ],
                }
            ),
        )

        p = self.load_policy(
            {
                "name": "sns-modify-add-policy-without-sid",
                "resource": "sns",
                "filters": [{"TopicArn": topic_arn}],
                "actions": [
                    {
                        "type": "modify-policy",
                        "add-statements": [
                            {
                                "Sid": "AddMe",
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": ["SNS:GetTopicAttributes"],
                                "Resource": topic_arn,
                            }
                        ],
                        "remove-statements": [],
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        data = json.loads(
            client.get_topic_attributes(TopicArn=resources[0]["TopicArn"])[
                "Attributes"
            ][
                "Policy"
            ]
        )
        self.assertEqual(len(data.get('Statement')), 2)
        self.assertTrue("AddMe" in [s.get("Sid") for s in data.get("Statement", ())])

    def test_sns_topic_encryption(self):
        session_factory = self.replay_flight_data('test_sns_kms_related_filter_test')
        kms = session_factory().client('kms', region_name='ap-northeast-2')
        p = self.load_policy(
            {
                'name': 'test-sns-kms-related-filter',
                'resource': 'sns',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'TopicArn',
                        'op': 'glob',
                        'value': '*encrypted*'
                    },
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/skunk/trails'
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['KmsMasterKeyId'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/skunk/trails')

    def test_set_sns_topic_encryption(self):
        session_factory = self.replay_flight_data('test_sns_set_encryption')
        topic = 'arn:aws:sns:ap-northeast-2:644160558196:test'
        p = self.load_policy(
            {
                'name': 'test-sns-kms-related-filter',
                'resource': 'sns',
                'filters': [
                    {
                        'TopicArn': topic
                    },
                    {
                        'KmsMasterKeyId': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'set-encryption'
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        sns = session_factory().client('sns', region_name='ap-northeast-2')
        attributes = sns.get_topic_attributes(TopicArn=topic)
        self.assertTrue(attributes['Attributes']['KmsMasterKeyId'], 'alias/aws/sns')

    def test_sns_disable_encryption(self):
        session_factory = self.replay_flight_data('test_sns_unset_encryption')
        topic = 'arn:aws:sns:ap-northeast-2:644160558196:test'
        p = self.load_policy(
            {
                'name': 'test-sns-kms-related-filter',
                'resource': 'sns',
                'filters': [
                    {
                        'TopicArn': topic
                    },
                    {
                        'KmsMasterKeyId': 'alias/aws/sns'
                    }
                ],
                'actions': [
                    {
                        'type': 'set-encryption',
                        'enabled': False
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)

        sns = session_factory().client('sns', region_name='ap-northeast-2')
        attributes = sns.get_topic_attributes(TopicArn=topic)['Attributes']
        self.assertFalse(attributes.get('KmsMasterKeyId'))

    def test_sns_set_encryption_custom_key(self):
        session_factory = self.replay_flight_data('test_sns_set_encryption_custom_key')
        topic = 'arn:aws:sns:ap-northeast-2:644160558196:test'
        key_alias = 'alias/skunk/trails'
        sns = session_factory().client('sns', region_name='ap-northeast-2')
        p = self.load_policy(
            {
                'name': 'test-sns-kms-related-filter-alias',
                'resource': 'sns',
                'filters': [
                    {
                        'TopicArn': topic
                    },
                    {
                        'KmsMasterKeyId': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'set-encryption',
                        'key': key_alias
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        attributes = sns.get_topic_attributes(TopicArn=topic)['Attributes']
        self.assertEqual(attributes.get('KmsMasterKeyId'), key_alias)

    def test_sns_delete(self):
        session_factory = self.replay_flight_data('test_sns_delete_topic')
        policy = """
        name: delete-sns
        resource: aws.sns
        filters:
          - TopicArn: arn:aws:sns:ap-northeast-2:644160558196:test
        actions:
          - type: delete
        """
        p = self.load_policy(
            yaml_load(policy),
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('sns', region_name='ap-northeast-2')
        resources = client.list_topics()['Topics']
        self.assertEqual(len(resources), 0)

    def test_sns_tag(self):
        session_factory = self.replay_flight_data("test_sns_tag")
        p = self.load_policy(
            {
                "name": "tag-sns",
                "resource": "sns",
                "filters": [{"tag:Tagging": "absent"}],
                "actions": [{"type": "tag", "key": "Tagging", "value": "added"}],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sns", region_name='ap-northeast-2')
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["TopicArn"])["Tags"]
        self.assertEqual(tags[0]["Value"], "added")

    def test_sns_remove_tag(self):
        session_factory = self.replay_flight_data(
            "test_sns_remove_tag")
        p = self.load_policy(
            {
                "name": "untag-sns",
                "resource": "sns",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                    }
                ],
                "actions": [{"type": "remove-tag", "tags": ["custodian_cleanup"]}],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sns", region_name='ap-northeast-2')
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["TopicArn"])["Tags"]
        self.assertEqual(len(tags), 0)

    def test_sns_mark_for_op(self):
        session_factory = self.replay_flight_data(
            "test_sns_mark_for_op"
        )
        p = self.load_policy(
            {
                "name": "sns-untagged-delete",
                "resource": "sns",
                "filters": [
                    {"tag:Tagging": "absent"},
                    {"tag:custodian_cleanup": "absent"},
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("sns", region_name='ap-northeast-2')
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["TopicArn"])["Tags"]
        self.assertTrue(tags[0]["Key"], "custodian_cleanup")

    def test_sns_post_finding(self):
        factory = self.replay_flight_data('test_sns_post_finding')
        p = self.load_policy({
            'name': 'sns',
            'resource': 'aws.sns',
            'actions': [
                {'type': 'post-finding',
                 'types': [
                     'Software and Configuration Checks/OrgStandard/abc-123']}]},
            session_factory=factory, config={'region': 'ap-northeast-2'})
        resources = p.resource_manager.get_resources([
            'arn:aws:sns:ap-northeast-2:644160558196:sandbox-relay'])
        rfinding = p.resource_manager.actions[0].format_resource(
            resources[0])
        self.assertEqual(
            rfinding,
            {'Details': {
                'AwsSnsTopic': {
                    'KmsMasterKeyId': 'arn:aws:kms:ap-northeast-2:644160558196:key/83a5b9da-e2ed-417c-b55b-894a75a8d140',  # noqa
                    'Owner': '644160558196',
                    'TopicName': 'sandbox-relay'}},
             'Id': 'arn:aws:sns:ap-northeast-2:644160558196:sandbox-relay',
             'Partition': 'aws',
             'Region': 'ap-northeast-2',
             'Type': 'AwsSnsTopic'})
        shape_validate(
            rfinding['Details']['AwsSnsTopic'],
            'AwsSnsTopicDetails', 'securityhub')

    def test_sns_config(self):
        session_factory = self.replay_flight_data("test_sns_config")
        p = self.load_policy(
            {"name": "sns-config",
             "source": "config",
             "resource": "sns"},
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['Tags'][0]['Value'], 'false')

    def test_sns_has_statement_definition(self):
        session_factory = self.replay_flight_data(
            "test_sns_has_statement"
        )
        p = self.load_policy(
            {
                "name": "test_sns_has_statement_definition",
                "resource": "sns",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": "SNS:Publish",
                                "Principal": "*",
                                "Condition":
                                    {"Bool": {"aws:SecureTransport": "false"}},
                                "Resource": "{topic_arn}"
                            }
                        ]
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["TopicArn"],
            "arn:aws:sns:ap-northeast-2:644160558196:sns-test-has-statement"
        )

    def test_sns_has_statement_star_definition(self):
        session_factory = self.replay_flight_data(
            "test_sns_has_statement"
        )
        p = self.load_policy(
            {
                "name": "test_sns_has_statement_star_definition",
                "resource": "sns",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": "*",
                                "Principal": "*",
                                "Condition":
                                    {"Bool": {"aws:SecureTransport": "false"}},
                                "Resource": "{topic_arn}"
                            }
                        ]
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["TopicArn"],
        "arn:aws:sns:ap-northeast-2:644160558196:sns-test-has-statement")

    def test_sns_has_statement_id(self):
        session_factory = self.replay_flight_data(
            "test_sns_has_statement"
        )
        p = self.load_policy(
            {
                "name": "test_sns_has_statement_id",
                "resource": "sns",
                "filters": [
                    {
                        "type": "has-statement",
                        "statement_ids": ["BlockNonSSL"]
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["TopicArn"],
        "arn:aws:sns:ap-northeast-2:644160558196:sns-test-has-statement")

    def test_sns_has_statement_multi_action(self):
        session_factory = self.replay_flight_data(
            "test_sns_has_statement"
        )
        client = session_factory().client("sns")
        name = "test_sns_has_statement_multi_action"
        topic_arn = client.create_topic(Name=name)["TopicArn"]

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Deny",
                            "Action": [
                                # IMPORTANT: These actions are intentionally ordered differently
                                # than in the policy. The point of this test is
                                # to ensure that the filter is order-agnostic.
                                "SNS:Publish",
                                "SNS:Subscribe",
                                "SNS:SetTopicAttributes"
                            ],
                            "Principal": "*",
                            "Condition":
                                {"Bool": {"aws:SecureTransport": "false"}},
                            "Resource": "{topic_arn}"
                        }
                    ],
                }
            ),
        )
        p = self.load_policy(
            {
                "name": "test_sns_has_statement_multi_action",
                "resource": "sns",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": [
                                    "SNS:SetTopicAttributes",
                                    "SNS:Publish",
                                    "SNS:Subscribe"
                                ],
                                "Principal": "*",
                                "Condition":
                                    {"Bool": {"aws:SecureTransport": "false"}},
                                "Resource": "{topic_arn}"
                            }
                        ]
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["TopicArn"],
            "arn:aws:sns:ap-northeast-2:644160558196:sns-test-has-statement"
        )

    def test_sns_metrics(self):
        session_factory = self.replay_flight_data(
            "test_sns_metrics"
        )
        p = self.load_policy(
            {
                "name": "test_sns_metrics",
                "resource": "sns",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "NumberOfMessagesPublished",
                        "statistics": "Sum",
                        "missing-value": 0,
                        "days": 30,
                        "value": 0,
                        "op": "eq",
                        "period": 2592000
                    }
                ],
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestSubscription(BaseTest):

    def test_subscription_delete(self):
        factory = self.replay_flight_data("test_subscription_delete")

        p = self.load_policy(
            {
                "name": "external-owner-delete",
                "resource": "sns-subscription",
                "filters": [
                    {
                        "type": "value",
                        "key": "Owner",
                        "value": "123456789099",
                        "op": "ne",
                    }
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertNotEqual(resources[0]["Owner"], "123456789099")
        client = factory().client("sns")
        subs = client.list_subscriptions()
        for s in subs.get("Subscriptions", []):
            self.assertTrue("123456789099" == s.get("Owner"))

    def test_subscription_unused(self):
        factory = self.replay_flight_data("test_subscription_unused")
        p = self.load_policy(
            {
               "name": "sns-subscription-unused",
               "resource": "sns-subscription",
               "filters": [
                   {
                     "type": "topic",
                     "key": "TopicArn",
                     "value": "absent"
                   }
               ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["TopicArn"],
        "arn:aws:sns:us-east-1:644160558196:test")
        self.assertEqual(resources[0]["c7n:Topic"][0],
        "arn:aws:sns:us-east-1:644160558196:test")
