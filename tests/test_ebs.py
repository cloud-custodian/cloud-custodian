# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
from unittest import mock
import datetime
from dateutil import parser

from botocore.exceptions import ClientError

from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.resources.aws import shape_validate
from c7n.resources.ebs import (
    CopyInstanceTags,
    EncryptInstanceVolumes,
    CopySnapshot,
    Delete,
    ErrorHandler,
    SnapshotQueryParser as QueryParser,
    VolumeQueryParser
)
from .common import BaseTest
from c7n.testing import mock_datetime_now


class SnapshotQueryParse(BaseTest):

    def test_query(self):
        qfilters = [
            {'Name': 'tag:Name', 'Values': ['Snapshot1']},
            {'Name': 'status', 'Values': ['completed']}]
        self.assertEqual(qfilters, QueryParser.parse(qfilters))

    def test_invalid_query(self):
        self.assertRaises(
            PolicyValidationError, QueryParser.parse, {})

        self.assertRaises(
            PolicyValidationError, QueryParser.parse, [None])

        self.assertRaises(
            PolicyValidationError, QueryParser.parse, [{'X': 1}])

        self.assertRaises(
            PolicyValidationError, QueryParser.parse, [
                {'Name': 'status', 'Values': 'completed'}])

        self.assertRaises(
            PolicyValidationError, QueryParser.parse, [
                {'Name': 'status', 'Values': ['Completed']}])

        self.assertRaises(
            PolicyValidationError, QueryParser.parse, [
                {'Name': 'snapshot-id', 'Values': [1]}])


class VolumeQueryParse(BaseTest):

    def test_query(self):
        qfilters = [
            {'Name': 'tag:Name', 'Values': ['Volume1']},
            {'Name': 'status', 'Values': ['available']}]
        self.assertEqual(qfilters, VolumeQueryParser.parse(qfilters))

    def test_query_encrypted(self):
        qfilters = [
            {'Name': 'encrypted', 'Values': ['true']},
            {'Name': 'volume-type', 'Values': ['gp3']}]
        self.assertEqual(qfilters, VolumeQueryParser.parse(qfilters))

    def test_query_attachment(self):
        qfilters = [
            {'Name': 'attachment.status', 'Values': ['attached']},
            {'Name': 'attachment.instance-id', 'Values': ['i-1234567890abcdef0']}]
        self.assertEqual(qfilters, VolumeQueryParser.parse(qfilters))

    def test_invalid_query(self):
        self.assertRaises(
            PolicyValidationError, VolumeQueryParser.parse, {})

        self.assertRaises(
            PolicyValidationError, VolumeQueryParser.parse, [None])

        self.assertRaises(
            PolicyValidationError, VolumeQueryParser.parse, [{'X': 1}])

        self.assertRaises(
            PolicyValidationError, VolumeQueryParser.parse, [
                {'Name': 'status', 'Values': 'available'}])

        self.assertRaises(
            PolicyValidationError, VolumeQueryParser.parse, [
                {'Name': 'status', 'Values': ['Available']}])

        self.assertRaises(
            PolicyValidationError, VolumeQueryParser.parse, [
                {'Name': 'volume-id', 'Values': [1]}])

        self.assertRaises(
            PolicyValidationError, VolumeQueryParser.parse, [
                {'Name': 'volume-type', 'Values': ['invalid-type']}])


class SnapshotErrorHandler(BaseTest):

    def test_tag_error(self):
        snaps = [{'SnapshotId': 'aa'}]
        error_response = {
            "Error": {
                "Message": "The snapshot 'aa' does not exist.",
                "Code": "InvalidSnapshot.NotFound",
            }
        }
        client = mock.MagicMock()
        client.create_tags.side_effect = ClientError(error_response, 'CreateTags')

        p = self.load_policy({
            "name": "snap-copy",
            "resource": "ebs-snapshot",
            'actions': [{'type': 'tag', 'tags': {'bar': 'foo'}}]})
        tagger = p.resource_manager.actions[0]
        tagger.process_resource_set(client, snaps, [{'Key': 'bar', 'Value': 'foo'}])
        client.create_tags.assert_called_once()

    def test_remove_snapshot(self):
        snaps = [{'SnapshotId': 'a'}, {'SnapshotId': 'b'}, {'SnapshotId': 'c'}]

        t1 = list(snaps)
        ErrorHandler.remove_snapshot('c', t1)
        self.assertEqual([t['SnapshotId'] for t in t1], ['a', 'b'])

        ErrorHandler.remove_snapshot('d', snaps)
        self.assertEqual(len(snaps), 3)

    def test_get_bad_snapshot_malformed(self):
        operation_name = "DescribeSnapshots"
        error_response = {
            "Error": {
                "Message": 'Invalid id: "snap-malformedsnap"',
                "Code": "InvalidSnapshotID.Malformed",
            }
        }
        e = ClientError(error_response, operation_name)
        snap = ErrorHandler.extract_bad_snapshot(e)
        self.assertEqual(snap, "snap-malformedsnap")

    def test_get_bad_snapshot_notfound(self):
        operation_name = "DescribeSnapshots"
        error_response = {
            "Error": {
                "Message": "The snapshot 'snap-notfound' does not exist.",
                "Code": "InvalidSnapshot.NotFound",
            }
        }
        e = ClientError(error_response, operation_name)
        snap = ErrorHandler.extract_bad_snapshot(e)
        self.assertEqual(snap, "snap-notfound")

    def test_get_bad_volume_malformed(self):
        operation_name = "DescribeVolumes"
        error_response = {
            "Error": {
                "Message": 'Invalid id: "vol-malformedvolume"',
                "Code": "InvalidVolumeID.Malformed",
            }
        }
        e = ClientError(error_response, operation_name)
        vol = ErrorHandler.extract_bad_volume(e)
        self.assertEqual(vol, "vol-malformedvolume")

    def test_get_bad_volume_notfound(self):
        operation_name = "DescribeVolumes"
        error_response = {
            "Error": {
                "Message": "The volume 'vol-notfound' does not exist.",
                "Code": "InvalidVolume.NotFound",
            }
        }
        e = ClientError(error_response, operation_name)
        vol = ErrorHandler.extract_bad_volume(e)
        self.assertEqual(vol, "vol-notfound")

    def test_snapshot_copy_related_tags_missing_volumes(self):
        factory = self.replay_flight_data(
            "test_ebs_snapshot_copy_related_tags_missing_volumes")
        p = self.load_policy(
            {
                "name": "copy-related-tags",
                "resource": "aws.ebs-snapshot",
                "filters": [{"tag:Test": "Test"}],
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "resource": "ebs",
                        "key": "VolumeId",
                        "tags": "*"
                    }
                ]
            },
            session_factory=factory
        )
        try:
            resources = p.run()
        except ClientError:
            # it should filter missing volume and not throw an error
            self.fail("This should have been handled in ErrorHandler.extract_bad_volume")
        self.assertEqual(len(resources), 1)
        try:
            factory().client("ec2").describe_volumes(
                VolumeIds=[resources[0]["VolumeId"]]
            )
        except ClientError as e:
            # this should not filter missing volume and will throw an error
            msg = e.response["Error"]["Message"]
            err = e.response["Error"]["Code"]
        self.assertEqual(err, "InvalidVolume.NotFound")
        self.assertEqual(msg, f"The volume '{resources[0]['VolumeId']}' does not exist.")


class SnapshotAccessTest(BaseTest):

    def test_snapshot_access(self):
        # pre conditions, 2 snapshots one shared to a separate account, and one
        # shared publicly. 2 non matching volumes, one not shared, one shared
        # explicitly to its own account.
        self.patch(CopySnapshot, "executor_factory", MainThreadExecutor)
        factory = self.replay_flight_data("test_ebs_cross_account")
        p = self.load_policy(
            {
                "name": "snap-copy",
                "resource": "ebs-snapshot",
                "filters": ["cross-account"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            {r["SnapshotId"]: r["c7n:CrossAccountViolations"] for r in resources},
            {"snap-7f9496cf": ["619193117841"], "snap-af0eb71b": ["all"]},
        )

    def test_snapshot_access_everyone_only(self):
        # pre conditions, 2 snapshots one shared to a separate account, and one
        # shared publicly. 2 non matching volumes, one not shared, one shared
        # explicitly to its own account.
        factory = self.replay_flight_data("test_ebs_cross_account")
        p = self.load_policy(
            {
                "name": "snap-copy",
                "resource": "ebs-snapshot",
                "filters": [
                    {
                        "type": "cross-account",
                        "everyone_only": True,
                    },
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {r["SnapshotId"]: r["c7n:CrossAccountViolations"] for r in resources},
            {"snap-af0eb71b": ["all"]},
        )


class SnapshotDetachTest(BaseTest):

    def test_volume_detach(self):
        factory = self.replay_flight_data('test_ebs_detach')
        p = self.load_policy(
            {
                'name': 'volume-detach',
                'resource': 'ebs',
                'filters': [{'VolumeId': 'vol-0850cf7c8e949c318'}],
                'actions': [
                    {
                        'type': 'detach'
                    }
                ]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = factory(region="us-east-1").client('ec2')
        volumelist = []
        volumelist.append(resources[0]['VolumeId'])
        response = client.describe_volumes(VolumeIds=volumelist)

        for resp in response['Volumes']:
            for attachment in resp['Attachments']:
                self.assertTrue(attachment['State'] == "detached" or
                                attachment['State'] == "detaching")


class SnapshotCopyTest(BaseTest):

    def test_snapshot_copy(self):
        self.patch(CopySnapshot, "executor_factory", MainThreadExecutor)
        self.change_environment(AWS_DEFAULT_REGION="us-west-2")

        factory = self.replay_flight_data("test_ebs_snapshot_copy")
        p = self.load_policy(
            {
                "name": "snap-copy",
                "resource": "ebs-snapshot",
                "filters": [{"tag:ASV": "RoadKill"}],
                "actions": [
                    {
                        "type": "copy",
                        "target_region": "us-east-1",
                        "target_key": "82645407-2faa-4d93-be71-7d6a8d59a5fc",
                    }
                ],
            },
            config=dict(region="us-west-2"),
            session_factory=factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        client = factory(region="us-east-1").client("ec2")
        tags = client.describe_tags(
            Filters=[
                {"Name": "resource-id", "Values": [resources[0]["c7n:CopiedSnapshot"]]}
            ]
        )[
            "Tags"
        ]
        tags = {t["Key"]: t["Value"] for t in tags}
        self.assertEqual(tags["ASV"], "RoadKill")


class SnapshotAmiSnapshotTest(BaseTest):

    def test_snapshot_ami_snapshot_filter(self):
        self.patch(CopySnapshot, "executor_factory", MainThreadExecutor)
        # DEFAULT_REGION needs to be set to west for recording
        factory = self.replay_flight_data("test_ebs_ami_snapshot_filter")

        # first case should return only resources that are ami snapshots
        p = self.load_policy(
            {
                "name": "ami-snap-filter",
                "resource": "ebs-snapshot",
                "filters": [{"type": "skip-ami-snapshots", "value": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)

        # second case should return resources that are NOT ami snapshots
        policy = self.load_policy(
            {
                "name": "non-ami-snap-filter",
                "resource": "ebs-snapshot",
                "filters": [{"type": "skip-ami-snapshots", "value": True}],
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)


class SnapshotUnusedTest(BaseTest):

    def test_snapshot_unused(self):
        factory = self.replay_flight_data("test_ebs_snapshot_unused")
        p = self.load_policy(
            {
                "name": "snap-unused",
                "resource": "ebs-snapshot",
                "filters": [{"type": "unused", "value": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        policy = self.load_policy(
            {
                "name": "snap-used",
                "resource": "ebs-snapshot",
                "filters": [{"type": "unused", "value": False}],
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)


class SnapshotTrimTest(BaseTest):

    def test_snapshot_trim(self):
        factory = self.replay_flight_data("test_ebs_snapshot_delete")
        p = self.load_policy(
            {
                "name": "snapshot-trim",
                "resource": "ebs-snapshot",
                "filters": [{"tag:InstanceId": "not-null"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class SnapshotSetPermissions(BaseTest):
    # The precondition to these tests in here is that we have an EBS
    # snapshot with create volume permissions for accounts
    # 112233445566 and 665544332211

    def test_reset(self):
        factory = self.replay_flight_data(
            "test_ebs_snapshot_set_permissions_reset")
        p = self.load_policy(
            {
                "name": "reset-permissions",
                "resource": "ebs-snapshot",
                "filters": ["cross-account"],
                "actions": ["set-permissions"],
            },
            session_factory=factory,
        )
        p.validate()
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert sorted(
            resources[0]['c7n:CrossAccountViolations']) == sorted(
                ['112233445566', '665544332211'])
        client = factory().client('ec2')
        perms = client.describe_snapshot_attribute(
            SnapshotId=resources[0]['SnapshotId'],
            Attribute='createVolumePermission')['CreateVolumePermissions']
        assert perms == []

    def test_add(self):
        # For this test, we assume only 665544332211 has permissions,
        # and we test adding 112233445566 and removing 665544332211
        factory = self.replay_flight_data(
            "test_ebs_snapshot_set_permissions_add")
        p = self.load_policy(
            {
                "name": "set-permissions",
                "resource": "ebs-snapshot",
                "filters": ["cross-account"],
                "actions": [
                    {
                        "type": "set-permissions",
                        "add": ["112233445566"],
                        "remove": ["665544332211"],
                    },
                ],
            },
            session_factory=factory,
        )
        p.validate()
        resources = p.run()

        self.assertEqual(len(resources), 1)
        client = factory().client('ec2')
        perms = client.describe_snapshot_attribute(
            SnapshotId=resources[0]['SnapshotId'],
            Attribute='createVolumePermission')['CreateVolumePermissions']
        assert perms == [
            {"UserId": "112233445566"},
        ]

    def test_matched(self):
        factory = self.replay_flight_data(
            "test_ebs_snapshot_set_permissions_matched")
        p = self.load_policy(
            {
                "name": "set-permissions",
                "resource": "ebs-snapshot",
                "filters": [
                    {
                        "type": "cross-account",
                        "whitelist": ["112233445566"],
                    },
                ],
                "actions": [
                    {
                        "type": "set-permissions",
                        "remove": "matched",
                    },
                ],
            },
            session_factory=factory,
        )
        p.validate()
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted(resources[0]['c7n:CrossAccountViolations']),
            ['665544332211'])

        client = factory().client('ec2')
        perms = client.describe_snapshot_attribute(
            SnapshotId=resources[0]['SnapshotId'],
            Attribute='createVolumePermission')['CreateVolumePermissions']
        assert perms == [{"UserId": "112233445566"}]

    def test_matched_everyone_only(self):
        factory = self.replay_flight_data(
            "test_ebs_snapshot_set_permissions_matched_everyone_only")
        p = self.load_policy(
            {
                "name": "snap-copy",
                "resource": "ebs-snapshot",
                "filters": [
                    {
                        "type": "cross-account",
                        "everyone_only": True,
                    },
                ],
                "actions": [
                    {
                        "type": "set-permissions",
                        "remove": "matched"
                    }
                ],
            },
            session_factory=factory,
        )
        p.validate()
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert resources[0]['SnapshotId'] == "snap-af0eb71b"
        client = factory().client('ec2')
        perms = client.describe_snapshot_attribute(
            SnapshotId=resources[0]['SnapshotId'],
            Attribute='createVolumePermission')['CreateVolumePermissions']
        assert perms == []


class SnapshotVolumeFilter(BaseTest):

    def test_ebs_volume_filter(self):
        factory = self.replay_flight_data("test_ebs_volume_related_filter")
        p = self.load_policy(
            {
                "name": "ebs-snapshot-volume",
                "resource": "aws.ebs-snapshot",
                "filters": [
                    {
                        "type": "volume",
                        "key": "AvailabilityZone",
                        "value": "us-east-1a"
                    }
                ]
            }, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class AttachedInstanceTest(BaseTest):

    def test_ebs_instance_filter(self):
        factory = self.replay_flight_data("test_ebs_instance_filter")
        p = self.load_policy(
            {
                "name": "attached-instance-test",
                "resource": "ebs",
                "filters": [
                    {"type": "instance", "key": "tag:Name", "value": "CompiledLambda"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class ResizeTest(BaseTest):

    def test_resize_action(self):
        factory = self.replay_flight_data("test_ebs_modifyable_action")
        client = factory().client("ec2")
        # Change a volume from 32 gb gp2 and 100 iops (sized based) to
        # 64gb and 500 iops.
        vol_id = "vol-0073dcd216489ea1b"
        p = self.load_policy(
            {
                "name": "resizable",
                "resource": "ebs",
                "filters": ["modifyable", {"VolumeId": vol_id}],
                "actions": [
                    {
                        "type": "modify",
                        "volume-type": "io1",
                        "size-percent": 200,
                        "iops-percent": 500,
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["Iops"], 100)
        self.assertEqual(resources[0]["Size"], 32)
        vol = client.describe_volumes(VolumeIds=[vol_id])["Volumes"][0]
        self.assertEqual(vol["Iops"], 500)
        self.assertEqual(vol["Size"], 64)

    def test_resize_filter(self):
        # precondition, 6 volumes, 4 not modifyable.
        factory = self.replay_flight_data("test_ebs_modifyable_filter")
        output = self.capture_logging("custodian.filters", level=logging.DEBUG)
        p = self.load_policy(
            {"name": "resizable", "resource": "ebs", "filters": ["modifyable"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(
            {r["VolumeId"] for r in resources},
            {"vol-0073dcd216489ea1b", "vol-0e4cba7adc4764f79"},
        )
        self.assertEqual(
            output.getvalue().strip(),
            ("filtered 4 of 6 volumes due to [('instance-type', 2), "
             "('vol-mutation', 1), ('vol-type', 1)]")
        )


class CopyInstanceTagsTest(BaseTest):

    def test_copy_instance_tags(self):
        # More a functional/coverage test then a unit test.
        self.patch(CopyInstanceTags, "executor_factory", MainThreadExecutor)
        factory = self.replay_flight_data("test_ebs_copy_instance_tags")

        volume_id = "vol-2b047792"

        results = factory().client("ec2").describe_tags(
            Filters=[{"Name": "resource-id", "Values": [volume_id]}]
        )[
            "Tags"
        ]
        tags = {t["Key"]: t["Value"] for t in results}
        self.assertEqual(tags, {})

        policy = self.load_policy(
            {
                "name": "test-copy-instance-tags",
                "resource": "ebs",
                "actions": [{"type": "copy-instance-tags", "tags": ["Name"]}],
            },
            config={"region": "us-west-2"},
            session_factory=factory,
        )

        policy.run()
        results = factory().client("ec2").describe_tags(
            Filters=[{"Name": "resource-id", "Values": [volume_id]}]
        )[
            "Tags"
        ]

        tags = {t["Key"]: t["Value"] for t in results}
        self.assertEqual(tags["Name"], "CompileLambda")


class VolumePostFindingTest(BaseTest):

    def test_volume_post_finding(self):
        factory = self.replay_flight_data('test_ebs_snapshot')
        p = self.load_policy({
            'name': 'vol-finding',
            'resource': 'aws.ebs',
            'actions': [{
                'type': 'post-finding',
                'types': [
                    'Software and Configuration Checks/OrgStandard/abc-123']}]},
            session_factory=factory)
        resources = p.resource_manager.resources()
        rfinding = p.resource_manager.actions[0].format_resource(
            resources[0])
        self.maxDiff = None
        self.assertEqual(
            rfinding,
            {'Details': {
                'AwsEc2Volume': {
                    'Attachments': [{'AttachTime': '2017-03-28T14:55:28+00:00',
                                     'DeleteOnTermination': True,
                                     'InstanceId': 'i-0a0b51bcf11a8cdfb',
                                     'Status': 'attached'}],
                    'CreateTime': '2017-03-28T14:55:28.486000+00:00',
                    'Size': 8,
                    'SnapshotId': 'snap-037f1f9e6c8ea4d65'}},
             'Id': 'arn:aws:ec2:us-east-1:644160558196:volume/vol-01adbb6a4f175941d',
             'Partition': 'aws',
             'Region': 'us-east-1',
             'Type': 'AwsEc2Volume'})
        shape_validate(
            rfinding['Details']['AwsEc2Volume'],
            'AwsEc2VolumeDetails', 'securityhub')


class VolumeSnapshotTest(BaseTest):

    def test_volume_snapshot(self):
        factory = self.replay_flight_data("test_ebs_snapshot")
        policy = self.load_policy(
            {
                "name": "test-ebs-snapshot",
                "resource": "ebs",
                "filters": [{"VolumeId": "vol-01adbb6a4f175941d"}],
                "actions": ["snapshot"],
            },
            session_factory=factory,
        )
        policy.run()
        snapshot_data = factory().client("ec2").describe_snapshots(
            Filters=[{"Name": "volume-id", "Values": ["vol-01adbb6a4f175941d"]}]
        )
        self.assertEqual(len(snapshot_data["Snapshots"]), 1)

    def test_volume_snapshot_copy_tags(self):
        factory = self.replay_flight_data("test_ebs_snapshot_copy_tags")
        policy = self.load_policy(
            {
                "name": "ebs-test-snapshot",
                "resource": "ebs",
                "filters": [{"VolumeId": "vol-0252f61378ede9d01"}],
                "actions": [{"type": "snapshot", "copy-tags": ['Name', 'Stage']}]
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        snapshot_data = factory().client("ec2").describe_snapshots(
            Filters=[{"Name": "volume-id", "Values": ["vol-0252f61378ede9d01"]}]
        )
        rtags = {t['Key']: t['Value'] for t in resources[0]['Tags']}
        rtags.pop('DoNotCopy')
        rtags['custodian_snapshot'] = ''
        for s in snapshot_data['Snapshots']:
            self.assertEqual(rtags, {t['Key']: t['Value'] for t in s['Tags']})

    def test_volume_snapshot_copy_volume_tags(self):
        factory = self.replay_flight_data("test_ebs_snapshot_copy_volume_tags")
        policy = self.load_policy(
            {
                "name": "ebs-test-snapshot",
                "resource": "ebs",
                "filters": [{"VolumeId": "vol-0252f61378ede9d01"}],
                "actions": [{"type": "snapshot",
                             "copy-volume-tags": False,
                             "tags": {'test-tag': 'custodian'}}]
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        snapshot_data = factory().client("ec2").describe_snapshots(
            Filters=[{"Name": "volume-id", "Values": ["vol-0252f61378ede9d01"]}]
        )
        for s in snapshot_data['Snapshots']:
            self.assertEqual({'test-tag': 'custodian'}, {t['Key']: t['Value'] for t in s['Tags']})

    def test_volume_snapshot_description(self):
        factory = self.replay_flight_data("test_ebs_snapshot_description")
        policy = self.load_policy(
            {
                "name": "ebs-test-snapshot",
                "resource": "ebs",
                "filters": [{"VolumeId": "vol-0cc137cb158adbc32"}],
                "actions": [{"type": "snapshot",
                             "description": "snapshot description"}]
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        snapshot_data = factory().client("ec2").describe_snapshots(
            Filters=[{"Name": "volume-id", "Values": ["vol-0cc137cb158adbc32"]}]
        )
        for s in snapshot_data['Snapshots']:
            self.assertEqual('snapshot description', s['Description'])

    def test_volume_snapshot_default_description(self):
        factory = self.replay_flight_data("test_ebs_snapshot_default_description")
        policy = self.load_policy(
            {
                "name": "ebs-test-snapshot",
                "resource": "ebs",
                "filters": [{"VolumeId": "vol-0cc137cb158adbc32"}],
                "actions": [{"type": "snapshot"}]
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        snapshot_data = factory().client("ec2").describe_snapshots(
            Filters=[{"Name": "volume-id", "Values": ["vol-0cc137cb158adbc32"]}]
        )
        for s in snapshot_data['Snapshots']:
            self.assertEqual('Automated snapshot by c7n - ebs-test-snapshot', s['Description'])


class VolumeDeleteTest(BaseTest):

    def test_volume_delete_force(self):
        self.patch(Delete, "executor_factory", MainThreadExecutor)
        factory = self.replay_flight_data("test_ebs_force_delete")
        policy = self.load_policy(
            {
                "name": "test-ebs",
                "resource": "ebs",
                "filters": [{"VolumeId": "vol-d0790258"}],
                "actions": [{"type": "delete", "force": True}],
            },
            session_factory=factory,
        )
        resources = policy.run()

        try:
            factory().client("ec2").describe_volumes(
                VolumeIds=[resources[0]["VolumeId"]]
            )
        except ClientError as e:
            self.assertEqual(e.response["Error"]["Code"], "InvalidVolume.NotFound")
        else:
            self.fail("Volume still exists")


class EncryptExtantVolumesTest(BaseTest):

    def test_encrypt_volumes(self):
        self.patch(EncryptInstanceVolumes, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_encrypt_volumes")
        policy = self.load_policy(
            {
                "name": "ebs-remediate-attached",
                "resource": "ebs",
                "filters": [
                    {"Encrypted": False}, {"VolumeId": "vol-0f53c81b92b4ecfce"}
                ],
                "actions": [
                    {
                        "type": "encrypt-instance-volumes",
                        "delay": 0.001,
                        "key": "alias/encryptebs",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        for r in resources:
            volumes = session_factory().client("ec2").describe_volumes(
                Filters=[
                    {
                        "Name": "attachment.instance-id",
                        "Values": [r["Attachments"][0]["InstanceId"]],
                    }
                ]
            )
            for v in volumes["Volumes"]:
                self.assertTrue(v["Attachments"][0]["DeleteOnTermination"])
                self.assertTrue(v["Encrypted"])
                if "Tags" in v:
                    self.assertNotIn(
                        "maid-crypt-remediation", [i["Key"] for i in v["Tags"]]
                    )
                    self.assertNotIn(
                        "maid-origin-volume", [i["Key"] for i in v["Tags"]]
                    )
                    self.assertNotIn(
                        "maid-instance-device", [i["Key"] for i in v["Tags"]]
                    )
                if (v["Attachments"][0]["InstanceId"] == r["Attachments"][0]["InstanceId"]):
                    self.assertEqual(v["Tags"], r["Tags"])


class TestKmsAlias(BaseTest):

    def test_ebs_kms_alias(self):
        session_factory = self.replay_flight_data("test_ebs_aws_managed_kms_keys")
        p = self.load_policy(
            {
                "name": "ebs-aws-managed-kms-keys-filters",
                "resource": "ebs",
                "filters": [
                    {
                        "type": "kms-alias",
                        "key": "AliasName",
                        "value": "^(alias/aws/)",
                        "op": "regex",
                    }
                ],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VolumeId"], "vol-14a3cd9d")


class EbsFaultToleranceTest(BaseTest):

    def test_ebs_fault_tolerant(self):
        session = self.replay_flight_data("test_ebs_fault_tolerant")
        policy = self.load_policy(
            {
                "name": "ebs-fault-tolerant",
                "resource": "ebs",
                "filters": ["fault-tolerant"],
            },
            session_factory=session,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VolumeId"], "vol-c5eaa459")

    def test_ebs_non_fault_tolerant(self):
        session = self.replay_flight_data("test_ebs_non_fault_tolerant")
        policy = self.load_policy(
            {
                "name": "ebs-non-fault-tolerant",
                "resource": "ebs",
                "filters": [{"type": "fault-tolerant", "tolerant": False}],
            },
            session_factory=session,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VolumeId"], "vol-abdb8d37")


class PiopsMetricsFilterTest(BaseTest):

    def test_metrics_validation(self):
        policy = self.load_policy(
            {
                "name": "ebs-metrics-test",
                "resource": "ebs",
                "filters": [{
                    "type": "metrics",
                    "name": "VOlumeConsumedReadWriteOps",
                    "value": 50,
                    "op": "gt"}]})
        metrics = policy.resource_manager.filters[0]
        metrics.data['statistics'] = 'p99'
        metrics.validate()
        metrics.data['statistics'] = 'p99.5'
        metrics.validate()
        metrics.data['statistics'] = 'pabc'
        try:
            metrics.validate()
        except PolicyValidationError:
            pass
        else:
            self.fail()

    def test_ebs_metrics_percent_filter(self):
        session = self.replay_flight_data("test_ebs_metrics_percent_filter")
        policy = self.load_policy(
            {
                "name": "ebs-unused-piops",
                "resource": "ebs",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "VolumeConsumedReadWriteOps",
                        "op": "lt",
                        "value": 50,
                        "statistics": "Maximum",
                        "days": 1,
                        "percent-attr": "Iops",
                    }
                ],
            },
            session_factory=session,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        policy = self.load_policy(
            {
                "name": "ebs-unused-piops",
                "resource": "ebs",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "VolumeConsumedReadWriteOps",
                        "op": "gt",
                        "value": 50,
                        "statistics": "Maximum",
                        "days": 1,
                        "percent-attr": "Iops",
                    }
                ],
            },
            session_factory=session,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 0)


class VolumeQueryFilterTest(BaseTest):

    def test_volume_query_parser_integration(self):
        policy = self.load_policy({
            "name": "ebs-query-test",
            "resource": "ebs",
            "query": [
                {"Name": "encrypted", "Values": ["true"]},
                {"Name": "volume-type", "Values": ["gp3"]}
            ]
        })
        self.assertIsNotNone(policy)
        self.assertEqual(
            policy.resource_manager.data.get('query'),
            [
                {"Name": "encrypted", "Values": ["true"]},
                {"Name": "volume-type", "Values": ["gp3"]}
            ]
        )

    def test_volume_query_api_call(self):
        policy = self.load_policy({
            "name": "ebs-query-test",
            "resource": "ebs",
            "query": [
                {"Name": "encrypted", "Values": ["true"]},
                {"Name": "volume-type", "Values": ["gp3"]},
                {"Name": "status", "Values": ["available"]}
            ]
        })
        
        with mock.patch.object(
            policy.resource_manager.source,
            'resources',
            return_value=[]
        ) as mock_resources:
            policy.run()
            
            mock_resources.assert_called_once()

    def test_volume_query_filter(self):
        factory = self.replay_flight_data("test_ebs_volume_query")
        policy = self.load_policy(
            {
                "name": "ebs-encrypted-volumes",
                "resource": "ebs",
                "query": [
                    {"Name": "encrypted", "Values": ["true"]},
                    {"Name": "volume-type", "Values": ["gp3"]}
                ]
            },
            session_factory=factory,
        )
        resources = policy.run()
        for r in resources:
            self.assertTrue(r.get('Encrypted'))
            self.assertEqual(r.get('VolumeType'), 'gp3')

    def test_volume_query_combined_filters(self):
        factory = self.replay_flight_data("test_ebs_volume_query_combined")
        policy = self.load_policy(
            {
                "name": "ebs-unencrypted-gp3",
                "resource": "ebs",
                "query": [
                    {"Name": "volume-type", "Values": ["gp3"]}
                ],
                "filters": [
                    {"Encrypted": False}
                ]
            },
            session_factory=factory,
        )
        resources = policy.run()
        for r in resources:
            self.assertEqual(r.get('VolumeType'), 'gp3')
            self.assertFalse(r.get('Encrypted'))


class HealthEventsFilterTest(BaseTest):

    def test_ebs_health_events_filter(self):
        session_factory = self.replay_flight_data("test_ebs_health_events_filter")
        policy = self.load_policy(
            {
                "name": "ebs-health-events-filter",
                "resource": "ebs",
                "filters": [{"type": "health-event", "types": ["AWS_EBS_VOLUME_LOST"]}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        for r in resources:
            self.assertTrue(
                ("c7n:HealthEvent" in r) and
                ("Description" in e for e in r["c7n:HealthEvent"])
            )


class EbsSnapshotsFilterTest(BaseTest):
    def test_filter_match(self):
        session_factory = self.replay_flight_data("test_ebs_volume_snapshots_filter")
        p = self.load_policy({
            "name": "ebs-volumes",
            "resource": "aws.ebs",
            "filters": [{
                "not": [{
                    "type": "snapshots",
                    "attrs": [{
                      "type": "value",
                      "key": "StartTime",
                      "value_type": "age",
                      "value": 2,
                      "op": "less-than"
                    }]
                }]
            }]
        }, session_factory=session_factory)
        with mock_datetime_now(parser.parse("2024-02-01T10:32:48.405000+00:00"),
                               datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VolumeId"], "vol-0c7930681fe5a17db")
