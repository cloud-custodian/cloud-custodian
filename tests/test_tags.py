# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Most tags tests within their corresponding resource tags, we use this
module to test some universal tagging infrastructure not directly exposed.
"""
import time
from freezegun import freeze_time
from mock import MagicMock, call

from c7n.tags import universal_retry, coalesce_copy_user_tags
from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.utils import yaml_load

from .common import BaseTest

import pytest
from pytest_terraform import terraform


@pytest.mark.audited
@terraform('tag_action_filter_call')
def test_tag_action_filter_call(test, tag_action_filter_call):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data('test_action_filter_call', region=aws_region)

    p = test.load_policy(
        {
            'name': 'delete_marked_for_op_tag',
            'resource': 'ec2',
            'filters': [
                {
                    'State.Name': 'running'
                },
                {
                    'type': 'marked-for-op',
                    'tag': 'action_tag',
                    'op': 'stop'
                }
            ],
            'actions': ['stop'],
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    test.assertEqual(len(resources), 1)

    stopped_ec2_instance_id = tag_action_filter_call['aws_instance.past_stop.id']
    if test.recording:
        time.sleep(0.25)
    ec2 = session_factory().resource('ec2')
    instance = ec2.Instance(stopped_ec2_instance_id)
    test.assertEqual(instance.state['Name'], 'stopping')


class TagInterpolationTest(BaseTest):
    def __tag_interpolation_helper(self, resource_name, resources):

        mock_factory = MagicMock()
        mock_factory.region = 'us-east-1'

        create_tags = mock_factory().client(resource_name).create_tags

        tag_resources = mock_factory().client('resourcegroupstaggingapi').tag_resources
        tag_resources.return_value = {}

        policy = self.load_policy(
            {
                "name": "test-tag-interpolation",
                "resource": resource_name,
                "actions": [
                    {
                        "type": "tag",
                        "tags": {
                            "tag_account_id": "{account_id}",
                            "tag_now": "{now}",
                            "tag_region": "{region}",
                        },
                    }
                ],
            },
            session_factory=mock_factory,
        )
        policy.expand_variables(policy.get_variables())
        policy.resource_manager.actions[0].process(resources)

        return (create_tags, tag_resources)

    @freeze_time("2022-06-27 12:34:56")
    def test_ec2_tag_interpolation(self):
        (create_tags, _) = self.__tag_interpolation_helper(
            'ec2', [{'InstanceId': 'i-12345'}]
        )
        create_tags.assert_called_once_with(
            Resources=['i-12345'],
            Tags=[
                {'Key': 'tag_account_id', 'Value': self.account_id},
                {'Key': 'tag_now', 'Value': '2022-06-27 12:34:56'},
                {'Key': 'tag_region', 'Value': 'us-east-1'},
            ],
            DryRun=False,
        )

    @freeze_time("2022-06-27 12:34:56")
    def test_rds_tag_interpolation(self):
        (_, tag_resources) = self.__tag_interpolation_helper(
            'rds', [{'DBInstanceIdentifier': 'xxx', 'DBInstanceArn': 'arn:xxx'}]
        )
        tag_resources.assert_called_once_with(
            ResourceARNList=['arn:xxx'],
            Tags={
                'tag_account_id': self.account_id,
                'tag_now': '2022-06-27 12:34:56',
                'tag_region': 'us-east-1',
            },
        )

    @freeze_time("2022-06-27 12:34:56")
    def test_kms_key_tag_interpolation(self):
        (_, tag_resources) = self.__tag_interpolation_helper(
            'kms-key', [{'KeyId': 'xxx', 'Arn': 'arn:xxx'}]
        )
        tag_resources.assert_called_once_with(
            ResourceARNList=['arn:xxx'],
            Tags={
                'tag_account_id': self.account_id,
                'tag_now': '2022-06-27 12:34:56',
                'tag_region': 'us-east-1',
            },
        )


class UniversalTagTest(BaseTest):

    def test_auto_tag_registration(self):
        try:
            self.load_policy({
                'name': 'sfn-auto',
                'resource': 'step-machine',
                'mode': {'type': 'cloudtrail',
                         'events': [{'ids': 'some', 'source': 'thing', 'event': 'wicked'}]},
                'actions': [{'type': 'auto-tag-user', 'tag': 'creator'}]})
        except Exception as e:
            self.fail('auto-tag policy failed to load %s' % e)

    def test_universal_augment_resource_missing_tags(self):
        session_factory = self.replay_flight_data('test_tags_universal_augment_missing_tags')
        cache_cluster_id = 'arn:aws:elasticache:us-east-1:644160558196:cluster:test'
        client = session_factory().client('elasticache')
        tags = client.list_tags_for_resource(ResourceName=cache_cluster_id)
        self.assertEqual(len(tags['TagList']), 0)
        policy = self.load_policy(
            {
                'name': 'elasticache-no-tags',
                'resource': 'cache-cluster',
                'filters': [
                    {'CacheClusterId': 'test'}
                ]
            },
            session_factory=session_factory
        )
        results = policy.run()
        self.assertTrue('Tags' in results[0])

    def test_retry_no_error(self):
        mock = MagicMock()
        mock.side_effect = [{"Result": 42}]
        self.assertEqual(universal_retry(mock, []), {"Result": 42})
        mock.assert_called_once()

    def test_retry_failure_reduced_set(self):
        sleep = MagicMock()
        self.patch(time, "sleep", sleep)
        method = MagicMock()
        method.side_effect = [
            {"FailedResourcesMap": {"arn:abc": {"ErrorCode": "ThrottlingException"}}},
            {"Result": 32},
        ]
        self.assertEqual(
            universal_retry(method, ["arn:abc", "arn:def"]), {"Result": 32}
        )
        sleep.assert_called_once()
        self.assertTrue(
            method.call_args_list == [
                call(ResourceARNList=["arn:abc", "arn:def"]),
                call(ResourceARNList=["arn:abc"]),
            ]
        )

    def test_retry_pass_error(self):
        method = MagicMock()
        method.side_effect = [
            {"FailedResourcesMap": {"arn:abc": {"ErrorCode": "PermissionDenied"}}}
        ]
        self.assertRaises(Exception, universal_retry, method, ["arn:abc"])

    def test_mark_for_op_deprecations(self):
        policy = self.load_policy({
            'name': 'dep-test',
            'resource': 'ec2',
            'actions': [{'type': 'mark-for-op', 'op': 'stop'}]})

        self.assertDeprecation(policy, """
            policy 'dep-test'
              actions:
                mark-for-op: optional fields deprecated (one of 'hours' or 'days' must be specified)
            """)

    def test_unmark_deprecations(self):
        policy = self.load_policy({
            'name': 'dep-test',
            'resource': 'ec2',
            'filters': [{'tag:foo': 'exists'}],
            'actions': [{'type': 'unmark', 'tags': ['foo']}]})

        self.assertDeprecation(policy, """
            policy 'dep-test'
              actions:
                remove-tag: alias 'unmark' has been deprecated
            """)


class CoalesceCopyUserTags(BaseTest):
    def test_copy_bool_user_tags(self):
        tags = [{'Key': 'test-key', 'Value': 'test-value'}]
        resource = {
            'Tags': tags
        }

        copy_tags = True
        user_tags = []

        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, tags)

        copy_tags = False
        user_tags = {'test-key-1': 'test-value'}

        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, [{'Key': 'test-key-1', 'Value': 'test-value'}])

    def test_copy_list_user_tags(self):
        tags = [
            {
                'Key': 'test-key-1',
                'Value': 'test-value'
            },
            {
                'Key': 'test-key',
                'Value': 'test-value'
            }
        ]
        resource = {
            'Tags': tags
        }

        copy_tags = ['test-key-1']
        user_tags = []

        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, [{'Key': 'test-key-1', 'Value': 'test-value'}])

    def test_copy_asterisk_user_tags(self):
        tags = [
            {
                'Key': 'test-key-1',
                'Value': 'test-value'
            },
            {
                'Key': 'test-key',
                'Value': 'test-value'
            }
        ]

        resource = {
            'Tags': tags
        }

        copy_tags = ['*']
        user_tags = []
        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, tags)

    def test_empty_resource_tags(self):
        resource = {}
        copy_tags = ['test-key-1']
        user_tags = {'user-key': 'test-value'}
        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, [{'Key': 'user-key', 'Value': 'test-value'}])

    def test_copy_user_tags_conflict(self):
        tags = [
            {
                'Key': 'test-key-1',
                'Value': 'test-value'
            },
            {
                'Key': 'test-key',
                'Value': 'test-value'
            }
        ]

        resource = {
            'Tags': tags
        }

        copy_tags = ['*']
        user_tags = [{'Key': 'test-key', 'Value': 'test-value-user'}]
        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(len(final_tags), 2)
        self.assertTrue({'Key': 'test-key-1', 'Value': 'test-value'} in final_tags)
        self.assertTrue({'Key': 'test-key', 'Value': 'test-value-user'} in final_tags)

    def test_empty_response(self):
        resource = {}
        user_tags = {}
        copy_tags = []
        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, [])


class CopyRelatedResourceTag(BaseTest):
    def test_copy_related_resource_tag_all(self):
        session_factory = self.replay_flight_data("test_tags_copy_related_resource_tags_all")
        p = self.load_policy(
            {
                "name": "copy-related-resource-tags-snapshots-volumes",
                "resource": "ebs-snapshot",
                "filters": [
                    {
                        "Tags": "empty"
                    }
                ],
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "resource": "ebs",
                        "key": "VolumeId",
                        "tags": "*"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('ec2', 'us-east-1')

        snap = client.describe_snapshots(SnapshotIds=[resources[0]['SnapshotId']])['Snapshots']
        vol = client.describe_volumes(VolumeIds=[resources[0]['VolumeId']])['Volumes']

        self.assertEqual(snap[0]['Tags'], vol[0]['Tags'])

    def test_copy_related_resource_tag_partial(self):
        session_factory = self.replay_flight_data("test_tags_copy_related_resource_tag_partial")
        p = self.load_policy(
            {
                "name": "copy-related-resource-tags-snapshots-volumes",
                "resource": "ebs-snapshot",
                "filters": [
                    {
                        "Tags": "empty"
                    }
                ],
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "resource": "ebs",
                        "key": "VolumeId",
                        "tags": [
                            "tag1",
                            "tag3"
                        ]
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('ec2', 'us-east-1')

        snap = client.describe_snapshots(SnapshotIds=[resources[0]['SnapshotId']])['Snapshots']
        vol = client.describe_volumes(VolumeIds=[resources[0]['VolumeId']])['Volumes']

        vol_tags = {t['Key']: t['Value'] for t in vol[0]['Tags']}
        snap_tags = {t['Key']: t['Value'] for t in snap[0]['Tags']}

        self.assertFalse(vol_tags == snap_tags)

        self.assertEqual(snap_tags['tag1'], vol_tags['tag1'])
        self.assertEqual(snap_tags['tag3'], vol_tags['tag3'])

        self.assertTrue(vol_tags['tag2'])
        self.assertFalse(snap_tags.get('tag2'))

    def test_copy_related_resource_tag_missing(self):
        session_factory = self.replay_flight_data("test_tags_copy_related_resource_tag_missing")
        p = self.load_policy(
            {
                "name": "copy-related-resource-tags-snapshots-volumes",
                "resource": "ebs-snapshot",
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "resource": "ebs",
                        "key": "VolumeId",
                        "skip_missing": False,
                        "tags": [
                            "*"
                        ]
                    }
                ]
            },
            session_factory=session_factory
        )

        with self.assertRaises(PolicyExecutionError):
            p.run()

    def test_copy_related_resource_tag_validate(self):
        p = self.load_policy(
            {
                "name": "copy-related-resource-tags-snapshots-volumes",
                "resource": "ebs-snapshot",
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "resource": "ebs",
                        "key": "VolumeId",
                        "skip_missing": False,
                        "tags": [
                            "*"
                        ]
                    }
                ]
            }
        )
        self.assertFalse(p.validate())

        policy = {
            "name": "copy-related-resource-tags-snapshots-volumes",
            "resource": "ebs-snapshot",
            "actions": [
                {
                    "type": "copy-related-tag",
                    "resource": "not-a-resource",
                    "key": "VolumeId",
                    "skip_missing": False,
                    "tags": [
                        "*"
                    ]
                }
            ]
        }
        self.assertRaises(PolicyValidationError, self.load_policy, policy)

    def test_copy_related_tag_empty(self):
        # check the case where the related expression doesn't return
        # value.
        output = self.capture_logging('custodian.actions')
        session_factory = self.replay_flight_data(
            'test_copy_related_resource_tag_empty')
        client = session_factory().client('ec2')
        p = self.load_policy({
            'name': 'copy-related-ec2',
            'resource': 'aws.eni',
            'actions': [{
                'type': 'copy-related-tag',
                'resource': 'ec2',
                'skip_missing': True,
                'key': 'Attachment.InstanceId',
                'tags': '*'}]},
            session_factory=session_factory)
        p.run()
        if self.recording:
            time.sleep(3)
        nics = client.describe_network_interfaces(
            NetworkInterfaceIds=['eni-0e1324ba169ed7b2f'])['NetworkInterfaces']
        self.assertEqual(
            nics[0]['TagSet'],
            [{'Key': 'Env', 'Value': 'Dev'},
             {'Key': 'Origin', 'Value': 'Home'}])
        self.assertEqual(
            output.getvalue().strip(),
            'Tagged 1 resources from related, missing-skipped 1 unchanged 0')

    def test_copy_related_resource_tag_multi_ref(self):
        session_factory = self.replay_flight_data('test_copy_related_resource_tag_multi_ref')
        client = session_factory().client('ec2')

        result = client.describe_volumes()['Volumes']
        self.assertEqual(len(result), 1)
        vol = result[0]

        self.assertEqual(vol['Tags'], [{'Key': 'test', 'Value': 'test'}])

        policy = """
        name: copy-tags-from-ebs-volume-to-snapshot
        resource: ebs-snapshot
        filters:
          - type: value
            key: Tags
            value: empty
        actions:
          - type: copy-related-tag
            resource: ebs
            skip_missing: True
            key: VolumeId
            tags: '*'
        """

        p = self.load_policy(yaml_load(policy), session_factory=session_factory)

        resources = p.run()

        self.assertEqual(len(resources), 3)

        if self.recording:
            time.sleep(10)

        all_snaps = client.describe_snapshots(OwnerIds=['self'])['Snapshots']

        self.assertEqual(len(all_snaps), 3)

        tagged_snaps = [e for e in all_snaps if e['VolumeId'] == vol['VolumeId']]
        untagged_snaps = [e for e in all_snaps if e['VolumeId'] != vol['VolumeId']]

        self.assertEqual(len(tagged_snaps), 2)
        self.assertEqual(tagged_snaps[0]['Tags'], vol['Tags'])
        self.assertEqual(tagged_snaps[1]['Tags'], vol['Tags'])

        self.assertEqual(len(untagged_snaps), 1)
        self.assertTrue('Tags' not in untagged_snaps[0].keys())

    def test_copy_related_tag_resourcegroupstaggingapi(self):
        session_factory = self.replay_flight_data("test_copy_related_tag_resourcegroupstaggingapi")
        ec2_client = session_factory().client("ec2")
        policy = {
            "name": "copy-tags-from-tags",
            "resource": "aws.ec2",
            "filters": [
                {
                    "type": "value",
                    "key": "tag:test-tag",
                    "value": "absent"
                },
            ],
            "actions": [
                {
                    "type": "copy-related-tag",
                    "resource": "resourcegroupstaggingapi",
                    "key": "tag:Foo",
                    "tags": "*"
                }
            ]
        }
        policy = self.load_policy(policy, session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        tags = ec2_client.describe_tags(
            Filters=[
                {
                    "Name": "resource-id",
                    "Values": [resources[0]['InstanceId']]
                }
            ]
        )
        found = False
        for t in tags["Tags"]:
            if t['Key'] == 'test-tag':
                found = True
        self.assertTrue(found)

    def test_copy_related_tag_validate_aws_prefix(self):
        policy = {
            'name': 'copy-related-tag-aws-prefix',
            'resource': 'ami',
            'actions': [
                {
                    'type': 'copy-related-tag',
                    'resource': 'aws.ebs-snapshot',
                    'key': '',
                    'tags': '*',
                }
            ]
        }
        # policy will validate on load
        policy = self.load_policy(policy)

    def test_copy_related_tag_validate_aws_prefix_fake_resource(self):
        policy = {
            'name': 'copy-related-tag-aws-prefix',
            'resource': 'ami',
            'actions': [
                {
                    'type': 'copy-related-tag',
                    'resource': 'aws.not-real',
                    'key': '',
                    'tags': '*',
                }
            ]
        }
        self.assertRaises(PolicyValidationError, self.load_policy, policy)
