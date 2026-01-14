# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
import functools
import json
import logging
import os
import io
import shutil
import tempfile
import time  # NOQA needed for some recordings
from unittest import mock

from unittest import TestCase

from contextlib import suppress
from botocore.exceptions import ClientError
from dateutil.tz import tzutc
import pytest
from pytest_terraform import terraform

from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.resources import s3
from c7n.mu import LambdaManager
from c7n.ufuncs import s3crypt
from c7n.utils import get_account_alias_from_sts, jmespath_search
import vcr

from .common import (
    BaseTest,
    ConfigTest,
    event_data,
    skip_if_not_validating,
    functional,
)


def test_s3_assembly_validate(test):

    for tcase in ('all', 'none', 'detect', ['Website', 'Replication']):
        policy = test.load_policy(
            {'name': 's3-attrs',
             'resource': 's3',
             'query': [{'augment-keys': tcase}]
             }
        )
        policy.validate()

    for tcase in ('random', ['Garbage'], {}):
        with pytest.raises(PolicyValidationError):
            policy = test.load_policy(
                {'name': 's3-attrs',
                 'resource': 's3',
                 'query': [{'augment-keys': tcase}],
                 'filters': [{'tag:Owner': 'xyz'}],
                 },
                validate=True
            )


def test_s3_assembly_none(test):
    # noting even with none we will still get location and tags to
    # ensure other s3 filters/actions work.
    policy = test.load_policy(
        {'name': 's3-attrs',
         'resource': 's3',
         'query': [{'augment-keys': 'none'}],
         'filters': [
             {'tag:Owner': 'xyz'},
         ]
         }
    )
    assembly = s3.BucketAssembly(policy.resource_manager)
    assert assembly.detect_augment_fields() == []


def test_s3_assembly_website(test):
    policy = test.load_policy(
        {'name': 's3-attrs',
         'resource': 's3',
         'query': [{'augment-keys': ['Website', 'Replication']}],
         'filters': [
             {'tag:Owner': 'xyz'},
         ]
         }
    )
    assembly = s3.BucketAssembly(policy.resource_manager)
    assert assembly.detect_augment_fields() == ['Website', 'Replication']


def test_s3_assembly_detect(test):

    policy = test.load_policy(
        {'name': 's3-attrs',
         'resource': 's3',
         'query': [{'augment-keys': 'detect'}],
         'filters': [
             {'tag:Owner': 'xyz'},
             {'type': 'cross-account'},
             {'SomethingRandom': 'xyz'},
             {'Replication.ReplicationConfiguation.Rules[].Destination.StorageClass': 'Standard'},
             {'type': 'value',
              'value': 'not-null',
              'key': 'Website.ErrorDocument'}]
         }
    )
    assembly = s3.BucketAssembly(policy.resource_manager)
    assert assembly.detect_augment_fields() == ['Tags', 'Replication', 'Website']


def test_s3_assembly_detect_denied(test):
    policy = test.load_policy(
        {'name': 's3-attrs',
         'resource': 's3',
         'query': [{'augment-keys': 'detect'}],
         'filters': [
             {'c7n:DeniedMethods': 'not-null'},
         ]}
    )
    assembly = s3.BucketAssembly(policy.resource_manager)
    assert assembly.detect_augment_fields() == [
        'Location', 'Tags', 'Policy', 'Acl', 'Replication', 'Versioning', 'Website',
        'Logging', 'Notification', 'Lifecycle']


def test_s3_express(test):
    session_factory = test.replay_flight_data('test_s3_express')
    p = test.load_policy(
        {'name': 's3-xpress',
         'resource': 's3-directory'},
        config={'account_id': '644160558196', 'region': 'us-east-1'},
        session_factory=session_factory)
    resources = p.run()
    assert len(resources) == 1
    assert p.resource_manager.get_arns(resources) == [
        'arn:aws:s3express:us-east-1:644160558196:bucket/test-zone--use1-az4--x-s3'
    ]


@pytest.mark.audited
@terraform('s3_tag')
def test_s3_tag(test, s3_tag):
    test.patch(s3.S3, "executor_factory", MainThreadExecutor)
    test.patch(s3.EncryptExtantKeys, "executor_factory", MainThreadExecutor)
    test.patch(
        s3, "S3_AUGMENT_TABLE", [("get_bucket_tagging", "Tags", [], "TagSet")]
    )
    session_factory = test.replay_flight_data("test_s3_tag")
    session = session_factory()
    client = session.client("s3")
    bucket_name = s3_tag['aws_s3_bucket.example.bucket']

    p = test.load_policy(
        {
            "name": "s3-tagger",
            "resource": "s3",
            "filters": [{"Name": bucket_name}],
            "actions": [
                {
                    "type": "tag",
                    "tags": {"new-tag": "new-value"},
                }
            ],
        },
        session_factory=session_factory,
    )

    resources = p.run()
    test.assertEqual(len(resources), 1)
    tags = {
        t["Key"]: t["Value"]
        for t in client.get_bucket_tagging(Bucket=bucket_name)["TagSet"]
    }
    test.assertEqual(
        {"original-tag": "original-value", "new-tag": "new-value"}, tags
    )


class RestoreCompletionTest(TestCase):

    def test_restore_complete(self):

        self.assertTrue(
            s3.restore_complete(
                (
                    'ongoing-request="false", '
                    'expiry-date="Fri, 23 Dec 2012 00:00:00 GMT"'
                )
            )
        )

        self.assertFalse(s3.restore_complete('ongoing-request="true"'))


class BucketScanLogTests(TestCase):

    def setUp(self):
        self.log_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.log_dir)
        self.log = s3.BucketScanLog(self.log_dir, "test")

    def test_scan_log(self):
        first_five = list(range(5))
        next_five = list(range(5, 10))
        with self.log:
            self.log.add(first_five)
            self.log.add(next_five)

        with open(self.log.path) as fh:
            data = json.load(fh)
            self.assertEqual(data, [first_five, next_five, []])


def destroyBucket(client, bucket):
    for o in client.list_objects(Bucket=bucket).get("Contents", []):
        client.delete_object(Bucket=bucket, Key=o["Key"])
    client.delete_bucket(Bucket=bucket)


def destroyVersionedBucket(client, bucket):
    for o in client.list_object_versions(Bucket=bucket).get("Versions", []):
        client.delete_object(Bucket=bucket, Key=o["Key"], VersionId=o["VersionId"])
    client.delete_bucket(Bucket=bucket)


def destroyBucketIfPresent(client, bucket):
    with suppress(client.exceptions.NoSuchBucket):
        destroyVersionedBucket(client, bucket)


def generateBucketContents(s3, bucket, contents=None):
    default_contents = {
        "home.txt": "hello", "AWSLogs/2015/10/10": "out", "AWSLogs/2015/10/11": "spot"
    }
    if contents is None:
        contents = default_contents
    s3.Bucket(bucket)
    for k, v in contents.items():
        key = s3.Object(bucket, k)
        key.put(Body=v, ContentLength=len(v), ContentType="text/plain")


class BucketMetrics(BaseTest):

    def test_metrics_dims(self):
        factory = self.replay_flight_data('test_s3_metrics_user_dims')
        p = self.load_policy({
            'name': 's3',
            'resource': 's3',
            'source': 'config',
            'query': [
                {'clause': "resourceId = 'c7n-ssm-build'"}],
            'filters': [{
                'type': 'metrics',
                'name': 'BucketSizeBytes',
                'dimensions': {
                    'StorageType': 'StandardStorage'},
                'days': 7,
                'value': 100,
                'op': 'gte'}]},
            session_factory=factory,
            config={'region': 'us-east-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('c7n.metrics', resources[0])
        assert p.resource_manager.get_arns(resources) == ['arn:aws:s3:::c7n-ssm-build']

    def test_metrics(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_metrics")
        p = self.load_policy(
            {
                "name": "s3-obj-count",
                "resource": "s3",
                "filters": [
                    {
                        "type": "metrics",
                        "value": 10000,
                        "name": "NumberOfObjects",
                        "op": "greater-than",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "custodian-skunk-trails")
        self.assertTrue("c7n.metrics" in resources[0])
        self.assertTrue("AWS/S3.NumberOfObjects.Average.14" in resources[0]["c7n.metrics"])


class BucketEncryption(BaseTest):

    def test_s3_bucket_encryption_filter(self):
        bname = "c7n-bucket-with-encryption"
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_bucket_encryption_filter")

        client = session_factory().client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(client.delete_bucket, Bucket=bname)

        enc = {
            "Rules": [
                {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ]
        }

        client.put_bucket_encryption(
            Bucket=bname, ServerSideEncryptionConfiguration=enc
        )

        p = self.load_policy(
            {
                "name": "s3-enc",
                "resource": "s3",
                "filters": [{"type": "bucket-encryption", "crypto": "AES256"}],
            },
            session_factory=session_factory,
        )
        resources = p.run() or []
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)

    def test_s3_bucket_encryption_filter_kms(self):
        def _get_encryption_config(key_id):
            default_encryption = {
                "SSEAlgorithm": "aws:kms"
            }
            if key_id:
                default_encryption["KMSMasterKeyID"] = key_id
            return {
                "Rules": [{
                    "ApplyServerSideEncryptionByDefault": default_encryption
                }]
            }

        bname_base = "c7n-bucket-with-encryption"
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data(
            "test_s3_bucket_encryption_filter_kms"
        )

        client = session_factory().client("s3")

        key_alias = "alias/aws/s3"
        key_meta = session_factory().client("kms").describe_key(KeyId=key_alias)["KeyMetadata"]
        key_arn = key_meta.get('Arn')
        alias_arn = ''.join((*key_arn.rpartition(':')[:2], key_alias))

        # Create separate buckets to test five ways of specifying the AWS-managed
        # KMS key for default server-side encryption.
        key_attrs = {
            'default': None,
            'aliasname': key_alias,
            'aliasarn': alias_arn,
            'keyid': key_meta.get('KeyId'),
            'keyarn': key_arn
        }

        for attr, value in key_attrs.items():
            # Create test buckets. Set a default encryption rule for each
            # one, using different attributes of the same key.
            bname = f'{bname_base}-by-{attr}'
            client.create_bucket(Bucket=bname)
            client.put_bucket_encryption(
                Bucket=bname,
                ServerSideEncryptionConfiguration=_get_encryption_config(value)
            )
            self.addCleanup(client.delete_bucket, Bucket=bname)

        p = self.load_policy(
            {
                "name": "s3-enc-kms",
                "resource": "s3",
                "filters": [
                    {
                        "type": "value",
                        "key": "Name",
                        "op": "glob",
                        "value": f"{bname_base}*",
                    },
                    {
                        "type": "bucket-encryption",
                        "crypto": "aws:kms",
                        "key": key_alias,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run() or []
        self.assertEqual(len(resources), len(key_attrs))

    def test_s3_filter_bucket_encryption_disabled(self):
        bname = "c7n-bucket-without-default-encryption"
        self.patch(s3.S3, "executor-factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_bucket_encryption_disabled")

        client = session_factory().client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(client.delete_bucket, Bucket=bname)

        p = self.load_policy(
            {
                "name": "s3-disabled-encryption",
                "resource": "s3",
                "filters": [
                    {"Name": bname}, {"type": "bucket-encryption", "state": False}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(ClientError, client.get_bucket_encryption, Bucket=bname)

        client.put_bucket_encryption(
            Bucket=bname,
            ServerSideEncryptionConfiguration={
                "Rules": [
                    {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
        )

        p = self.load_policy(
            {
                "name": "s3-disabled-encryption",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {"type": "bucket-encryption", "state": False, "crypto": "AES256"},
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_s3_filter_bucket_encryption_disabled_malformed_statement(self):
        bname = "xcc-services-alb-access-logs-prod-eu-central-1"
        self.patch(s3.S3, "executor-factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data(
            "test_s3_filter_bucket_encryption_disabled_malformed_statement"
        )

        p = self.load_policy(
            {
                "name": "s3-disabled-encryption-malformed-statement",
                "resource": "s3",
                "filters": [
                    {"Name": bname}, {"type": "bucket-encryption", "state": False}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_s3_bucket_encryption_bucket_key(self):
        session_factory = self.replay_flight_data("test_s3_bucket_encryption_bucket_key")

        bname = "custodian-test-bucket-encryption-key"

        self.patch(s3.S3, "executor-factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        policy = self.load_policy(
            {
                "name": "test_s3_bucket_encryption_bucket_key",
                "resource": "s3",
                "filters": [
                    {
                        "Name": bname
                    },
                    {
                        "type": "bucket-encryption",
                        "state": False
                    }
                ],
                "actions": [
                    {
                        "type": "set-bucket-encryption"
                    }
                ]
            }, session_factory=session_factory
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("s3")
        resp = client.get_bucket_encryption(Bucket=bname)
        self.assertTrue(resp['ServerSideEncryptionConfiguration']['Rules'][0]['BucketKeyEnabled'])


class BucketInventory(BaseTest):

    def test_s3_set_encrypted_inventory_sses3(self):
        bname = "custodian-inventory-test"
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data(
            "test_s3_set_encrypted_inventory_sses3"
        )

        client = session_factory().client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(client.delete_bucket, Bucket=bname)

        p = self.load_policy(
            {
                "name": "s3-inv",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {
                        "type": "set-inventory",
                        "destination": "inv-dest",
                        "name": "inv-name",
                        "state": "enabled",
                        "encryption": "SSES3",
                        "fields": ["Size", "EncryptionStatus"],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        invs = client.list_bucket_inventory_configurations(Bucket=bname).get(
            "InventoryConfigurationList"
        )
        self.assertTrue(invs)
        self.assertTrue(
            "SSES3" in invs[0]["Destination"]["S3BucketDestination"]["Encryption"]
        )
        self.assertTrue("EncryptionStatus" in invs[0]["OptionalFields"])

    def test_s3_set_encrypted_inventory_ssekms(self):
        bname = "custodian-inventory-test"
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data(
            "test_s3_set_encrypted_inventory_ssekms"
        )

        client = session_factory().client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(client.delete_bucket, Bucket=bname)

        p = self.load_policy(
            {
                "name": "s3-inv",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {
                        "type": "set-inventory",
                        "destination": "inv-dest",
                        "name": "inv-name",
                        "state": "enabled",
                        "encryption": "SSEKMS",
                        "key_id": "arn:valid:kms",
                        "fields": ["Size", "EncryptionStatus"],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        invs = client.list_bucket_inventory_configurations(Bucket=bname).get(
            "InventoryConfigurationList"
        )
        self.assertTrue(invs)
        self.assertTrue(
            "SSEKMS" in invs[0]["Destination"]["S3BucketDestination"]["Encryption"]
        )
        self.assertTrue("EncryptionStatus" in invs[0]["OptionalFields"])

    def test_s3_delete_inventory_inventory_not_set(self):
        bname = "delete_inventory"
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data(
            "test_s3_delete_inventory_inventory_not_set"
        )

        client = session_factory().client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(client.delete_bucket, Bucket=bname)

        p = self.load_policy(
            {
                "name": "s3-inv",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {
                        "type": "set-inventory",
                        "destination": "inv-dest",
                        "name": "inv-name",
                        "state": "absent",
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        inventoryConfigList = client.list_bucket_inventory_configurations(
            Bucket=bname
        ).get(
            "InventoryConfigurationList"
        )
        self.assertFalse(inventoryConfigList)

    @functional
    def test_inventory(self):
        bname = "custodian-test-data"
        inv_bname = "custodian-inv"
        inv_name = "something"

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_inventory")

        client = session_factory().client("s3")
        if self.recording:
            destroyBucketIfPresent(client, bname)
            destroyBucketIfPresent(client, inv_bname)
        client.create_bucket(
            Bucket=bname, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        client.create_bucket(
            Bucket=inv_bname,
            CreateBucketConfiguration={"LocationConstraint": "us-east-2"},
        )

        self.addCleanup(client.delete_bucket, Bucket=bname)
        self.addCleanup(client.delete_bucket, Bucket=inv_bname)

        inv = {
            "Destination": {
                "S3BucketDestination": {
                    "Bucket": "arn:aws:s3:::%s" % inv_bname,
                    "Format": "CSV",
                    "Prefix": "abcdef",
                }
            },
            "IsEnabled": True,
            "Id": inv_name,
            "IncludedObjectVersions": "All",
            "OptionalFields": ["LastModifiedDate"],
            "Schedule": {"Frequency": "Daily"},
        }

        client.put_bucket_inventory_configuration(
            Bucket=bname, Id=inv_name, InventoryConfiguration=inv
        )

        p = self.load_policy(
            {
                "name": "s3-inv",
                "resource": "s3",
                "filters": [{"Name": "custodian-test-data"}],
                "actions": [
                    {
                        "type": "set-inventory",
                        "destination": inv_bname,
                        "name": inv_name,
                    }
                ],
            },
            session_factory=session_factory,
        )
        self.assertEqual(len(p.run()), 1)
        invs = client.list_bucket_inventory_configurations(Bucket=bname).get(
            "InventoryConfigurationList"
        )
        self.assertTrue(invs)
        self.assertEqual(
            sorted(invs[0]["OptionalFields"]), ["LastModifiedDate", "Size"]
        )

        p = self.load_policy(
            {
                "name": "s3-inv",
                "resource": "s3",
                "filters": [{"Name": "custodian-test-data"}],
                "actions": [
                    {
                        "type": "set-inventory",
                        "destination": inv_bname,
                        "state": "absent",
                        "name": inv_name,
                    }
                ],
            },
            session_factory=session_factory,
        )

        self.assertEqual(len(p.run()), 1)
        self.assertFalse(
            client.list_bucket_inventory_configurations(Bucket=bname).get(
                "InventoryConfigurationList"
            )
        )


class BucketDelete(BaseTest):

    def test_delete_replicated_bucket(self):
        # the iam setup is a little for replication to duplicate in a test
        # preconditions - custodian-replicated and custodian-replicated-west
        # buckets setup with replication, we're deleting the custodian-replicated
        # bucket (source).
        bname = "custodian-replicated"
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [
                ("get_bucket_replication", "Replication", None, None),
                ("get_bucket_versioning", "Versioning", None, None),
            ],
        )
        session_factory = self.replay_flight_data("test_s3_delete_replicated_bucket")
        p = self.load_policy(
            {
                "name": "s3-delete-bucket",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "delete", "remove-contents": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        session = session_factory()
        client = session.client("s3")
        buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}
        self.assertFalse(bname in buckets)

    @functional
    def test_delete_versioned_bucket(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_versioning", "Versioning", None, None)],
        )
        session_factory = self.replay_flight_data("test_s3_delete_versioned_bucket")
        session = session_factory()
        client = session.client("s3")
        s3_resource = session.resource("s3")
        bname = "custodian-byebye"
        if self.recording:
            destroyBucketIfPresent(client, bname)
        client.create_bucket(
            Bucket=bname, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        client.put_bucket_versioning(
            Bucket=bname, VersioningConfiguration={"Status": "Enabled"}
        )
        generateBucketContents(s3_resource, bname)
        # Generate some versions
        generateBucketContents(s3_resource, bname)

        upload_info = client.create_multipart_upload(Bucket=bname, Key="abcdef12345")
        client.upload_part(
            Body="1" * 1024,
            Bucket=bname,
            Key="abcdef12345",
            PartNumber=1,
            UploadId=upload_info["UploadId"],
        )

        p = self.load_policy(
            {
                "name": "s3-delete-bucket",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "delete", "remove-contents": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        if self.recording:
            time.sleep(60)
        self.assertEqual(len(resources), 1)
        buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}
        self.assertFalse(bname in buckets)

    @functional
    def test_delete_bucket(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.DeleteBucket, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_delete_bucket")
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-byebye"

        if self.recording:
            destroyBucketIfPresent(client, bname)
        client.create_bucket(
            Bucket=bname, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        generateBucketContents(session.resource("s3"), bname)

        p = self.load_policy(
            {
                "name": "s3-delete-bucket",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "delete", "remove-contents": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}
        self.assertFalse(bname in buckets)

    def test_delete_bucket_with_failure(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.DeleteBucket, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_delete_bucket_with_failure")
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-perm-denied"
        client.create_bucket(Bucket=bname)
        generateBucketContents(session.resource("s3"), bname)

        # This bucket policy prevents viewing contents
        policy = {
            "Version": "2012-10-17",
            "Id": "Policy1487359365244",
            "Statement": [
                {
                    "Sid": "Stmt1487359361981",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:DeleteBucket",
                    "Resource": "arn:aws:s3:::{}".format(bname),
                }
            ],
        }
        client.put_bucket_policy(Bucket=bname, Policy=json.dumps(policy))

        p = self.load_policy(
            {
                "name": "s3-delete-bucket",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "delete", "remove-contents": True}],
            },
            output_dir=None,
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}
        self.assertIn(bname, buckets)

        # Make sure file got written
        denied_file = os.path.join(p.ctx.log_dir, "denied.json")
        self.assertIn(bname, open(denied_file).read())
        #
        # Now delete it for real
        #
        client.delete_bucket_policy(Bucket=bname)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}
        self.assertFalse(bname in buckets)


class S3ConfigSource(ConfigTest):

    maxDiff = None

    def test_normalize_initial_state(self):
        """Check for describe/config parity after bucket creation, before changing properties"""

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        augments = list(s3.S3_AUGMENT_TABLE)
        augments.remove((
            "get_bucket_location", "Location", {}, None, 's3:GetBucketLocation'))
        self.patch(s3, "S3_AUGMENT_TABLE", augments)

        bname = "custodian-test-s3confignormalize"
        session_factory = self.replay_flight_data("test_s3_normalize_initstate", region="us-east-1")
        session = session_factory()

        queue_url = self.initialize_config_subscriber(session)
        client = session.client("s3")
        if self.recording:
            destroyBucketIfPresent(client, bname)
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        p = self.load_policy(
            {"name": "s3-inv", "resource": "s3", "filters": [{"Name": bname}]},
            session_factory=session_factory,
        )

        manager = p.load_resource_manager()
        resource_a = manager.get_resources([bname])[0]
        results = self.wait_for_config(session, queue_url, bname)
        resource_b = s3.ConfigS3(manager).load_resource(results[0])
        self.maxDiff = None
        self.assertEqual(s3.get_region(resource_b), 'us-east-1')
        for k in ("Logging", "Policy", "Versioning", "Name", "Website"):
            self.assertEqual(resource_a[k], resource_b[k])

        self.assertEqual(
            {t["Key"]: t["Value"] for t in resource_a.get("Tags")},
            {t["Key"]: t["Value"] for t in resource_b.get("Tags")},
        )

    @functional
    def test_normalize(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        augments = list(s3.S3_AUGMENT_TABLE)
        augments.remove((
            "get_bucket_location", "Location", {}, None, 's3:GetBucketLocation'))
        self.patch(s3, "S3_AUGMENT_TABLE", augments)

        bname = "custodian-test-data-23"
        session_factory = self.replay_flight_data("test_s3_normalize")
        session = session_factory()

        queue_url = self.initialize_config_subscriber(session)
        client = session.client("s3")
        if self.recording:
            destroyBucketIfPresent(client, bname)
        client.create_bucket(
            Bucket=bname, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        self.addCleanup(destroyBucket, client, bname)

        sns = session.client("sns")
        notify_topic = sns.create_topic(Name=bname).get("TopicArn")
        sns.set_topic_attributes(
            TopicArn=notify_topic,
            AttributeName="Policy",
            AttributeValue=json.dumps(
                {
                    "Statement": [
                        {
                            "Action": "SNS:Publish",
                            "Effect": "Allow",
                            "Resource": notify_topic,
                            "Principal": {"Service": "s3.amazonaws.com"},
                        }
                    ]
                }
            ),
        )
        self.addCleanup(sns.delete_topic, TopicArn=notify_topic)

        public = "http://acs.amazonaws.com/groups/global/AuthenticatedUsers"
        client.put_bucket_acl(
            Bucket=bname,
            AccessControlPolicy={
                "Owner": {
                    "DisplayName": "mandeep.bal",
                    "ID": "e7c8bb65a5fc49cf906715eae09de9e4bb7861a96361ba79b833aa45f6833b15",
                },
                "Grants": [
                    {"Grantee": {"Type": "Group", "URI": public}, "Permission": "READ"},
                    {
                        "Grantee": {
                            "Type": "Group",
                            "URI": "http://acs.amazonaws.com/groups/s3/LogDelivery",
                        },
                        "Permission": "WRITE",
                    },
                    {
                        "Grantee": {
                            "Type": "Group",
                            "URI": "http://acs.amazonaws.com/groups/s3/LogDelivery",
                        },
                        "Permission": "READ_ACP",
                    },
                ],
            },
        )
        client.put_bucket_tagging(
            Bucket=bname,
            Tagging={
                "TagSet": [
                    {"Key": "rudolph", "Value": "rabbit"},
                    {"Key": "platform", "Value": "tyre"},
                ]
            },
        )
        client.put_bucket_logging(
            Bucket=bname,
            BucketLoggingStatus={
                "LoggingEnabled": {"TargetBucket": bname, "TargetPrefix": "s3-logs/"}
            },
        )
        client.put_bucket_versioning(
            Bucket=bname, VersioningConfiguration={"Status": "Enabled"}
        )
        client.put_bucket_accelerate_configuration(
            Bucket=bname, AccelerateConfiguration={"Status": "Enabled"}
        )
        client.put_bucket_website(
            Bucket=bname,
            WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}},
        )
        client.put_bucket_policy(
            Bucket=bname,
            Policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "Zebra",
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:PutObject",
                            "Resource": "arn:aws:s3:::%s/*" % bname,
                            "Condition": {
                                "StringNotEquals": {
                                    "s3:x-amz-server-side-encryption": [
                                        "AES256", "aws:kms"
                                    ]
                                }
                            },
                        }
                    ],
                }
            ),
        )
        client.put_bucket_notification_configuration(
            Bucket=bname,
            NotificationConfiguration={
                "TopicConfigurations": [
                    {
                        "Id": bname,
                        "TopicArn": notify_topic,
                        "Events": ["s3:ObjectCreated:*"],
                        "Filter": {
                            "Key": {
                                "FilterRules": [{"Name": "prefix", "Value": "s3-logs/"}]
                            }
                        },
                    }
                ]
            },
        )

        p = self.load_policy(
            {"name": "s3-inv", "resource": "s3", "filters": [{"Name": bname}]},
            session_factory=session_factory,
        )

        manager = p.load_resource_manager()
        resource_a = manager.get_resources([bname])[0]
        results = self.wait_for_config(session, queue_url, bname)
        resource_b = s3.ConfigS3(manager).load_resource(results[0])
        self.maxDiff = None
        self.assertEqual(s3.get_region(resource_b), 'us-east-1')
        for k in ("Logging", "Policy", "Versioning", "Name", "Website"):
            self.assertEqual(resource_a[k], resource_b[k])

        self.assertEqual(
            {t["Key"]: t["Value"] for t in resource_a.get("Tags")},
            {t["Key"]: t["Value"] for t in resource_b.get("Tags")},
        )

    def test_config_normalize_notification(self):
        event = event_data("s3-rep-and-notify.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        resource = source.load_resource(event)
        self.assertEqual(s3.get_region(resource), 'us-east-1')
        self.assertEqual(
            resource["Notification"],
            {
                u"TopicConfigurations": [
                    {
                        u"Filter": {
                            u"Key": {
                                u"FilterRules": [{u"Name": "Prefix", u"Value": "oids/"}]
                            }
                        },
                        u"Id": "rabbit",
                        u"TopicArn": "arn:aws:sns:us-east-1:644160558196:custodian-test-data-22",
                        u"Events": [
                            "s3:ReducedRedundancyLostObject",
                            "s3:ObjectCreated:CompleteMultipartUpload",
                        ],
                    }
                ],
                u"LambdaFunctionConfigurations": [
                    {
                        u"Filter": {
                            u"Key": {
                                u"FilterRules": [{u"Name": "Prefix", u"Value": "void/"}]
                            }
                        },
                        u"LambdaFunctionArn": (
                            "arn:aws:lambda:us-east-1:644160558196:function:lambdaenv"
                        ),
                        u"Id": "ZDAzZDViMTUtNGU3MS00ZWIwLWI0MzgtOTZiMWQ3ZWNkZDY1",
                        u"Events": ["s3:ObjectRemoved:Delete"],
                    }
                ],
                u"QueueConfigurations": [
                    {
                        u"Filter": {
                            u"Key": {
                                u"FilterRules": [
                                    {u"Name": "Prefix", u"Value": "images/"}
                                ]
                            }
                        },
                        u"Id": "OGQ5OTAyNjYtYjBmNy00ZTkwLWFiMjUtZjE4ODBmYTgwNTE0",
                        u"QueueArn": "arn:aws:sqs:us-east-1:644160558196:test-queue",
                        u"Events": ["s3:ObjectCreated:*"],
                    }
                ],
            },
        )

    def test_config_handle_missing_attr(self):
        # test for bug of
        # https://github.com/cloud-custodian/cloud-custodian/issues/7808
        event = event_data("s3-from-rule-sans-accelerator.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        resource_config = json.loads(event["invokingEvent"])["configurationItem"]
        resource = source.load_resource(resource_config)
        assert resource['Name'] == 'c7n-fire-logs'

    def test_config_normalize_lifecycle_null_predicate(self):
        event = event_data("s3-lifecycle-null-predicate.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        resource = source.load_resource(event)
        rule = resource["Lifecycle"]["Rules"][0]
        self.assertEqual(
            rule,
            {
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
                "Expiration": {"Days": 1},
                "ID": "RemoveAbortedUploads",
                "NoncurrentVersionExpiration": {"NoncurrentDays": -1},
                "Status": "Enabled",
            },
        )

    def test_config_normalize_lifecycle_and_predicate(self):
        event = event_data("s3-lifecycle-and-predicate.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        resource = source.load_resource(event)
        rfilter = resource["Lifecycle"]["Rules"][0]["Filter"]

        self.assertEqual(rfilter["And"]["Prefix"], "docs/")
        self.assertEqual(
            rfilter["And"]["Tags"],
            [
                {"Value": "Archive", "Key": "Workflow"},
                {"Value": "Complete", "Key": "State"},
            ],
        )

    def test_config_normalize_lifecycle(self):
        event = event_data("s3-lifecycle.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        resource = source.load_resource(event)
        self.assertEqual(
            resource["Lifecycle"],
            {
                "Rules": [
                    {
                        "Status": "Enabled",
                        "NoncurrentVersionExpiration": {"NoncurrentDays": 545},
                        "Filter": {"Prefix": "docs/"},
                        "Transitions": [{"Days": 30, "StorageClass": "STANDARD_IA"}],
                        "Expiration": {"ExpiredObjectDeleteMarker": True},
                        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                        "NoncurrentVersionTransitions": [
                            {"NoncurrentDays": 180, "StorageClass": "GLACIER"}
                        ],
                        "ID": "Docs",
                    }
                ]
            },
        )

    def test_config_normalize_replication(self):
        event = event_data("s3-rep-and-notify.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        resource = source.load_resource(event)
        self.assertEqual(
            resource["Replication"],
            {
                u"ReplicationConfiguration": {
                    u"Rules": [
                        {
                            u"Status": "Enabled",
                            u"Prefix": "",
                            u"Destination": {
                                u"Account": "000111222333",
                                u"Bucket": "arn:aws:s3:::testing-west"},
                            u"ID": "testing-99",
                        }
                    ],
                    u"Role": (
                        "arn:aws:iam::644160558196:role"
                        "/custodian-replicated-custodian-replicated"
                        "-west-s3-repl-role"
                    ),
                }
            },
        )

    def test_config_normalize_website_redirect(self):
        event = event_data("s3-website-redirect.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        self.maxDiff = None
        resource = source.load_resource(event)
        self.assertEqual(
            resource["Website"],
            {
                "RedirectAllRequestsTo": {
                    "HostName": "www.google.com/", "Protocol": "https"
                }
            },
        )

    def test_config_normalize_website(self):
        event = event_data("s3-website.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        self.maxDiff = None
        resource = source.load_resource(event)
        self.assertEqual(
            resource["Website"],
            {
                u"IndexDocument": {u"Suffix": "index.html"},
                u"RoutingRules": [
                    {
                        u"Redirect": {u"ReplaceKeyWith": "error.html"},
                        u"Condition": {
                            u"HttpErrorCodeReturnedEquals": "404",
                            u"KeyPrefixEquals": "docs/",
                        },
                    }
                ],
            },
        )

    def test_load_item_resource(self):
        event = event_data("s3.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        self.maxDiff = None
        resource = source.load_resource(event)
        resource.pop("CreationDate")
        self.assertEqual(
            {"Planet": "Earth", "Verbose": "Game"},
            {t["Key"]: t["Value"] for t in resource.pop("Tags")},
        )
        self.assertEqual(s3.get_region(resource), 'us-east-2')
        self.assertEqual(
            resource,
            {
                "Location": {"LocationConstraint": u"us-east-2"},
                "Name": u"config-rule-sanity",
                "Lifecycle": None,
                "Website": None,
                "Policy": None,
                "Replication": None,
                "Versioning": None,
                "Logging": None,
                "Notification": None,
                "Acl": {
                    "Owner": {
                        "ID": u"e7c8bb65a5fc49cf906715eae09de9e4bb7861a96361ba79b833aa45f6833b15"
                    },
                    "Grants": [
                        {
                            "Grantee": {
                                "Type": "CanonicalUser",
                                "ID": (
                                    "e7c8bb65a5fc49cf906715eae09de"
                                    "9e4bb7861a96361ba79b833aa45f6833b15"
                                ),
                            },
                            "Permission": "FULL_CONTROL",
                        }
                    ],
                },
            },
        )

    def test_load_item_resource_config_event(self):
        event = event_data("s3-from-rule.json", "config")
        p = self.load_policy({"name": "s3cfg", "resource": "s3"})
        source = p.resource_manager.get_source("config")
        self.maxDiff = None

        resource_config = json.loads(event["invokingEvent"])["configurationItem"]
        resource = source.load_resource(resource_config)
        self.assertEqual(
            resource,
            {
                u"Acl": {
                    u"Grants": [
                        {
                            u"Grantee": {
                                u"ID": (
                                    "e7c8bb65a5fc49cf906715eae09de9e4"
                                    "bb7861a96361ba79b833aa45f6833b15"
                                ),
                                u"Type": u"CanonicalUser",
                            },
                            u"Permission": u"FULL_CONTROL",
                        }
                    ],
                    u"Owner": {
                        u"DisplayName": u"mandeep.bal",
                        u"ID": u"e7c8bb65a5fc49cf906715eae09de9e4bb7861a96361ba79b833aa45f6833b15",
                    },
                },
                u"CreationDate": datetime.datetime(
                    2017, 9, 15, 2, 5, 40, tzinfo=tzutc()
                ),
                u"Lifecycle": None,
                u"Location": {},
                u"Logging": {},
                u"Name": u"c7n-fire-logs",
                u"Notification": {},
                u"Policy": None,
                u"Replication": None,
                u"Tags": [],
                u"Versioning": {},
                u"Website": None,
            },
        )


class BucketPolicyStatements(BaseTest):

    @functional
    def test_policy(self):
        bname = "custodian-test-data"
        sid = "CustodianTest"

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )

        session_factory = self.replay_flight_data("test_s3_policy_statements")

        client = session_factory().client("s3")
        if self.recording:
            destroyBucketIfPresent(client, bname)
        client.create_bucket(
            Bucket=bname, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )

        self.addCleanup(client.delete_bucket, Bucket=bname)

        p = self.load_policy(
            {
                "name": "s3-policy-statements",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {
                        "type": "set-statements",
                        "statements": [
                            {
                                "Sid": sid,
                                "Effect": "Deny",
                                "Action": "s3:GetObject",
                                "Principal": {"AWS": "*"},
                                "Resource": "arn:aws:s3:::{bucket_name}/*",
                                "Condition": {"Bool": {"aws:SecureTransport": False}},
                            }
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )
        self.assertEqual(len(p.run()), 1)

        policy = client.get_bucket_policy(Bucket=bname).get("Policy")
        policy = json.loads(policy)

        self.assertTrue(len(policy["Statement"]) > 0)
        self.assertTrue(
            len([s for s in policy["Statement"] if s["Sid"] == sid and
                s["Resource"] == "arn:aws:s3:::%s/*" % (bname)]) == 1
        )

    @functional
    def test_policy_no_change(self):
        bname = "custodian-test-data"

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )

        session_factory = self.replay_flight_data("test_s3_policy_statements_no_change")

        client = session_factory().client("s3")
        if self.recording:
            destroyBucketIfPresent(client, bname)
        client.create_bucket(
            Bucket=bname, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )

        self.addCleanup(client.delete_bucket, Bucket=bname)

        p = self.load_policy(
            {
                "name": "s3-policy-statements",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "set-statements", "statements": []}],
            },
            session_factory=session_factory,
        )
        self.assertEqual(len(p.run()), 1)


class S3Test(BaseTest):

    def test_bucket_get_resources(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [
            ('get_bucket_tagging', 'Tags', [], 'TagSet')])
        session_factory = self.replay_flight_data("test_s3_get_resources")
        p = self.load_policy(
            {"name": "bucket-fetch", "resource": "s3"},
            session_factory=session_factory)
        resources = p.resource_manager.get_resources(['c7n-codebuild'])
        self.assertEqual(len(resources), 1)
        tags = {t['Key']: t['Value'] for t in resources[0].get('Tags')}
        self.assertEqual(
            tags, {
                'Application': 'test', 'Env': 'Dev', 'Owner': 'nicholase',
                'Retention': '2', 'Retention2': '3', 'test': 'test'})
        self.assertTrue("CreationDate" in resources[0])

    def test_multipart_large_file(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.EncryptExtantKeys, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        self.patch(s3, "MAX_COPY_SIZE", (1024 * 1024 * 6.1))
        session_factory = self.replay_flight_data("test_s3_multipart_file")
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-largef-test"
        key = "hello"
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        class wrapper:

            def __init__(self, d, length):
                self.d = d
                self.len = length
                self.counter = length

            def read(self, size):
                if self.counter == 0:
                    return ""
                if size > self.counter:
                    size = self.counter
                    self.counter = 0
                else:
                    self.counter -= size
                return self.d.read(size)

            def seek(self, offset, whence=0):
                if whence == 2 and offset == 0:
                    self.counter = 0
                elif whence == 0 and offset == 0:
                    self.counter = self.len

            def tell(self):
                return self.len - self.counter

        size = 1024 * 1024 * 16
        client.put_object(
            Bucket=bname,
            Key=key,
            Metadata={"planet": "earth"},
            Body=wrapper(io.BytesIO(bytearray(size)), size),
            ContentLength=size,
        )
        info = client.head_object(Bucket=bname, Key=key)
        p = self.load_policy(
            {
                "name": "encrypt-obj",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": ["encrypt-keys"],
            },
            output_dir=None,
            session_factory=session_factory,
        )
        p.run()
        post_info = client.head_object(Bucket=bname, Key="hello")
        self.assertTrue("ServerSideEncryption" in post_info)
        self.assertEqual(post_info["Metadata"], {"planet": "earth"})
        # etags on multipart do not reflect md5 :-(
        self.assertTrue(info["ContentLength"], post_info["ContentLength"])

    def test_self_log(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_logging", "Logging", None, "LoggingEnabled")],
        )
        session_factory = self.replay_flight_data("test_s3_self_log_target")
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-log-test"
        client.create_bucket(Bucket=bname)
        self.addCleanup(client.delete_bucket, Bucket=bname)
        client.put_bucket_acl(
            Bucket=bname,
            AccessControlPolicy={
                "Owner": {
                    "DisplayName": "k_vertigo",
                    "ID": "904fc4c4790937100e9eb293a15e6a0a1f265a064888055b43d030034f8881ee",
                },
                "Grants": [
                    {
                        "Grantee": {
                            "Type": "Group",
                            "URI": "http://acs.amazonaws.com/groups/s3/LogDelivery",
                        },
                        "Permission": "WRITE",
                    },
                    {
                        "Grantee": {
                            "Type": "Group",
                            "URI": "http://acs.amazonaws.com/groups/s3/LogDelivery",
                        },
                        "Permission": "READ_ACP",
                    },
                ],
            },
        )
        client.put_bucket_logging(
            Bucket=bname,
            BucketLoggingStatus={
                "LoggingEnabled": {"TargetBucket": bname, "TargetPrefix": "s3-logs/"}
            },
        )
        p = self.load_policy(
            {
                "name": "s3-log-targets",
                "resource": "s3",
                "filters": [{"Name": bname}, {"type": "is-log-target", "self": True}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        names = [b["Name"] for b in resources]
        self.assertEqual(names[0], bname)
        self.assertEqual(len(names), 1)

    def test_log_target(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_logging", "Logging", None, "LoggingEnabled")],
        )
        session_factory = self.replay_flight_data("test_s3_log_target")
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-log-test"
        client.create_bucket(Bucket="custodian-log-test")
        self.addCleanup(client.delete_bucket, Bucket=bname)
        client.put_bucket_acl(
            Bucket=bname,
            AccessControlPolicy={
                "Owner": {
                    "DisplayName": "k_vertigo",
                    "ID": "904fc4c4790937100e9eb293a15e6a0a1f265a064888055b43d030034f8881ee",
                },
                "Grants": [
                    {
                        "Grantee": {
                            "Type": "Group",
                            "URI": "http://acs.amazonaws.com/groups/s3/LogDelivery",
                        },
                        "Permission": "WRITE",
                    },
                    {
                        "Grantee": {
                            "Type": "Group",
                            "URI": "http://acs.amazonaws.com/groups/s3/LogDelivery",
                        },
                        "Permission": "READ_ACP",
                    },
                ],
            },
        )
        client.put_bucket_logging(
            Bucket=bname,
            BucketLoggingStatus={
                "LoggingEnabled": {"TargetBucket": bname, "TargetPrefix": "s3-logs/"}
            },
        )
        p = self.load_policy(
            {"name": "s3-log-targets", "resource": "s3", "filters": ["is-log-target"]},
            session_factory=session_factory,
        )
        resources = p.run()
        names = [b["Name"] for b in resources]
        self.assertTrue(bname in names)

    def test_has_statement(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3.MissingPolicyStatementFilter, "executor_factory", MainThreadExecutor
        )
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        session_factory = self.replay_flight_data("test_s3_has_statement")
        bname = "custodian-policy-test"
        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        client.put_bucket_policy(
            Bucket=bname,
            Policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "Zebra",
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:PutObject",
                            "Resource": "arn:aws:s3:::%s/*" % bname,
                            "Condition": {
                                "StringNotEquals": {
                                    "s3:x-amz-server-side-encryption": [
                                        "AES256", "aws:kms"
                                    ]
                                }
                            },
                        },
                        {
                            "Sid": "Zebra2",
                            "Effect": "Deny",
                            "Principal": "arn:aws:iam::644160558196:root",
                            "Action": "s3:PutObject",
                            "Resource": "arn:aws:s3:::%s/*" % bname,
                        },
                    ],
                }
            ),
        )
        p = self.load_policy(
            {
                "name": "s3-has-policy",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {"type": "has-statement", "statement_ids": ["Zebra"]},
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_has_statement_policy(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3.MissingPolicyStatementFilter, "executor_factory", MainThreadExecutor
        )
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        session_factory = self.replay_flight_data("test_s3_has_statement")
        bname = "custodian-policy-test"
        p = self.load_policy(
            {
                "name": "s3-has-policy",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": "s3:PutObject",
                                "Principal": "*",
                                "Resource": "arn:aws:s3:::{bucket_name}/*"
                            }
                        ],
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_has_statement_policy_action_star(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3.MissingPolicyStatementFilter, "executor_factory", MainThreadExecutor
        )
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        session_factory = self.replay_flight_data("test_s3_has_statement")
        bname = "custodian-policy-test1"
        p = self.load_policy(
            {
                "name": "s3-has-policy",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": "*",
                                "Principal": "*",
                                "Resource": "arn:aws:s3:::{bucket_name}/*"
                            }
                        ],
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_has_statement_policy_partial(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3.MissingPolicyStatementFilter, "executor_factory", MainThreadExecutor
        )
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        session_factory = self.replay_flight_data("test_s3_has_statement")
        bname = "custodian-policy-test"
        p = self.load_policy(
            {
                "name": "s3-has-policy",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": ["s3:PutObject"],
                                "PartialMatch": ["Action"]
                            }
                        ],
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_bucket_replication_policy_remove(self):
        replicated_from_name = "replication-from-12345"

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)

        # only augment with logging info to minimize API calls
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_replication", 'Replication',
            None, None, 's3:GetReplicationConfiguration')],
        )

        # and ignore any other buckets we might have in this test account
        # to minimize the placebo data and API calls
        # Inspired by #5206, thanks tjstansell!
        self.patch(
            s3.S3.resource_type,
            "enum_spec",
            ('list_buckets', "Buckets[?Name=='{}']".format(replicated_from_name), None)
        )
        session_factory = self.replay_flight_data("test_s3_replication_policy_remove")
        session = session_factory()
        client = session.client("s3")

        p = self.load_policy(
            {
                "name": "s3-has-replica-policy",
                "resource": "s3",
                "filters": [
                    {
                        "type": "value",
                        "key": "Replication.ReplicationConfiguration.Rules[].Destination",
                        "value": "present"
                    },
                    {
                        "type": "value",
                        "key": "Replication.ReplicationConfiguration.Rules[].Status",
                        "value": "Enabled",
                        "op": "contains"
                    }
                ],
                "actions": [
                    {
                        "type": "set-replication",
                        "state": "remove"
                    }
                ]
            },
            session_factory=session_factory,
        )

        # Test that there was a bucket with an enabled replication policy
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Test to make sure that the replication policy removed from the buckets
        self.assertRaises(ClientError, client.get_bucket_replication, Bucket=replicated_from_name)

    def test_bucket_replication_policy_disable(self):
        bname = "repela"
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_replication", 'Replication',
            None, None, 's3:GetReplicationConfiguration')],
        )
        self.patch(
            s3.S3.resource_type,
            "enum_spec",
            ('list_buckets', "Buckets[?Name=='{}']".format(bname), None)
        )
        session_factory = self.replay_flight_data("test_s3_replication_policy_disable")
        session = session_factory()
        client = session.client("s3")
        p = self.load_policy(
            {
                "name": "s3-has-replica-policy",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "value",
                        "key": "Replication.ReplicationConfiguration.Rules[].Destination",
                        "value": "present"
                    },
                    {
                        "type": "value",
                        "key": "Replication.ReplicationConfiguration.Rules[].Status",
                        "value": "Enabled",
                        "op": "contains"
                    }
                ],
                "actions": [
                    {
                        "type": "set-replication",
                        "state": "disable"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()

        # Test that there was a bucket with an enabled replication policy
        self.assertEqual(len(resources), 1)

        # Test that there is a disbled policy on the bucket now
        response = client.get_bucket_replication(Bucket=bname)
        for rule in response['ReplicationConfiguration']['Rules']:
            self.assertEqual(rule['Status'], 'Disabled')

    def test_check_public_block(self):
        """Handle cases where public block details are missing or unavailable

        The default check-public-block filter should match buckets
        in any of the following conditions:

        - There is a public block configuration, but some settings are not
          enabled
        - There is no public block configuration set
        - A strict bucket policy prevents Custodian from reading the public block configuration
        """
        self.patch(s3.FilterPublicBlock, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_check_public_block")
        p = self.load_policy(
            {
                "name": "check-public-block",
                "resource": "s3",
                "filters": [
                    {
                        "type": "check-public-block",
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = {bucket["Name"]: bucket for bucket in p.run()}
        self.assertEqual(len(resources), 3)
        locked_down_bucket = resources["my-locked-down-bucket"]
        self.assertIn("GetPublicAccessBlock", locked_down_bucket["c7n:DeniedMethods"])

    def test_set_public_block_enable_all(self):
        bname = 'mypublicblock'

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_public_block_enable_all")
        session = session_factory()
        client = session.client("s3")

        p = self.load_policy(
            {
                "name": "CheckForPublicBlocks-Absent",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "check-public-block",
                    }
                ],
                "actions": [
                    {
                        "type": "set-public-block"
                    }
                ]
            },
            session_factory=session_factory,
        )

        # Test that there was a bucket with missing public blocks
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)

        # Make sure that all blocks are set to on/enabled now
        response = client.get_public_access_block(
            Bucket=bname)['PublicAccessBlockConfiguration']
        for key in response.keys():
            self.assertEqual(response[key], True)

    def test_set_public_block_disable_all(self):
        bname = 'mypublicblock'

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_public_block_disable_all")
        session = session_factory()
        client = session.client("s3")

        p = self.load_policy(
            {
                "name": "CheckForPublicBlocks-Present",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "check-public-block",
                        "BlockPublicAcls": True
                    }
                ],
                "actions": [
                    {
                        "type": "set-public-block",
                        "BlockPublicAcls": False,
                        "IgnorePublicAcls": False,
                        "BlockPublicPolicy": False,
                        "RestrictPublicBuckets": False
                    }
                ]
            },
            session_factory=session_factory,
        )

        # Test that there was a bucket with missing public blocks
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)

        # Make sure that the public blocks are disabled on the buckets
        response = client.get_public_access_block(
            Bucket=bname)['PublicAccessBlockConfiguration']
        for key in response.keys():
            self.assertEqual(response[key], False)

    def test_set_public_block_disable_all_via_state(self):
        bname = 'mypublicblock'

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_public_block_disable_all")
        session = session_factory()
        client = session.client("s3")

        p = self.load_policy(
            {
                "name": "CheckForPublicBlocks-Present",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "check-public-block",
                        "BlockPublicAcls": True
                    }
                ],
                "actions": [
                    {
                        "type": "set-public-block",
                        "state": False
                    }
                ]
            },
            session_factory=session_factory,
        )

        # Test that there was a bucket with missing public blocks
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)

        # Make sure that the public blocks are disabled on the buckets
        response = client.get_public_access_block(
            Bucket=bname)['PublicAccessBlockConfiguration']
        for key in response.keys():
            self.assertEqual(response[key], False)

    def test_set_public_block_enable_one(self):
        bname = 'mypublicblock'

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_public_block_enable_one")
        session = session_factory()
        client = session.client("s3")

        p = self.load_policy(
            {
                "name": "CheckForPublicBlocks-Absent",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "check-public-block",
                        "BlockPublicPolicy": False
                    }
                ],
                "actions": [
                    {
                        "type": "set-public-block",
                        "BlockPublicPolicy": True
                    }
                ]
            },
            session_factory=session_factory,
        )

        # Test that there was a bucket with BlockPublicAcls public block turned off
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)
        self.assertEqual(resources[0]["c7n:PublicAccessBlock"]["BlockPublicPolicy"], False)

        # Make sure that BlockPublicAcls public block turned on now
        assert client.get_public_access_block(
            Bucket=bname)['PublicAccessBlockConfiguration'] == {
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": False}

    def test_set_public_block_disable_one(self):
        bname = 'mypublicblock'

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_public_block_disable_one")
        session = session_factory()
        client = session.client("s3")

        p = self.load_policy(
            {
                "name": "CheckForPublicBlocks-Absent",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "check-public-block",
                        "IgnorePublicAcls": True
                    }
                ],
                "actions": [
                    {
                        "type": "set-public-block",
                        "IgnorePublicAcls": False
                    }
                ]
            },
            session_factory=session_factory,
        )

        # Test that there was a bucket with the IgnorePublicAcls public block set to on
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)
        self.assertEqual(resources[0]["c7n:PublicAccessBlock"]["IgnorePublicAcls"], True)

        # Make sure that the IgnorePublicAcls public block set to off
        assert client.get_public_access_block(
            Bucket=bname)['PublicAccessBlockConfiguration'] == {
                'BlockPublicAcls': False,
                'BlockPublicPolicy': True,
                'IgnorePublicAcls': False,
                'RestrictPublicBuckets': False}

    def test_set_public_block_throws_errors(self):
        bname = 'mypublicblock'

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])

        session_factory = self.replay_flight_data("test_s3_public_block_throws_errors")
        session = session_factory()
        client = session.client("s3")

        p = self.load_policy(
            {
                "name": "CheckForPublicBlocks-Absent",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "check-public-block",
                        "BlockPublicAcls": False,
                        "IgnorePublicAcls": False,
                        "BlockPublicPolicy": False,
                        "RestrictPublicBuckets": False
                    }
                ],
                "actions": [
                    {"type": "set-public-block"}
                ]
            },
            session_factory=session_factory,
        )

        # Test that there was a bucket with no public blocks
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)

        # Because there are no public blocks we will get a client error
        # We want this to throw for code cov
        try:
            client.get_public_access_block(Bucket=bname)['PublicAccessBlockConfiguration']
        except ClientError as e:
            # Assert that it is the proper error code
            self.assertEqual(e.response['Error']['Code'], 'NoSuchPublicAccessBlockConfiguration')

    def test_has_statement_similar_policies(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3.MissingPolicyStatementFilter, "executor_factory", MainThreadExecutor
        )
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        session_factory = self.replay_flight_data("test_s3_has_statement")
        bname = "custodian-policy-test"

        p = self.load_policy(
            {
                "name": "s3-has-policy",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "has-statement",
                        "statements": [{"Effect": "Deny", "Action": "s3:PutObject"}],
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_no_encryption_statement(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3.MissingPolicyStatementFilter, "executor_factory", MainThreadExecutor
        )
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        session_factory = self.replay_flight_data("test_s3_no_encryption_statement")
        bname = "custodian-encryption-test"
        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        client.put_bucket_policy(
            Bucket=bname,
            Policy=json.dumps(
                {
                    "Version": "2017-3-28",
                    "Statement": [
                        {
                            "Sid": "RequiredEncryptedObject",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": "s3:PutObject",
                            "Resource": "arn:aws:s3:::%s/*" % bname,
                            "Condition": {
                                "StringNotEquals": {
                                    "s3:x-amz-server-side-encryption": [
                                        "AES256", "aws:kms"
                                    ]
                                }
                            },
                        }
                    ],
                }
            ),
        )
        p = self.load_policy(
            {
                "name": "s3-no-encryption-policy",
                "resource": "s3",
                "filters": [{"Name": bname}, {"type": "no-encryption-statement"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_missing_policy_statement(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3.MissingPolicyStatementFilter, "executor_factory", MainThreadExecutor
        )
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        session_factory = self.replay_flight_data("test_s3_missing_policy")
        bname = "custodian-encrypt-test"
        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        client.put_bucket_policy(
            Bucket=bname,
            Policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "Zebra",
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:PutObject",
                            "Resource": "arn:aws:s3:::%s/*" % bname,
                            "Condition": {
                                "StringNotEquals": {
                                    "s3:x-amz-server-side-encryption": [
                                        "AES256", "aws:kms"
                                    ]
                                }
                            },
                        }
                    ],
                }
            ),
        )
        p = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "missing-policy-statement",
                        "statement_ids": ["RequireEncryptedPutObject"],
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_enable_versioning(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_versioning", "Versioning", None, None)],
        )
        session_factory = self.replay_flight_data("test_s3_enable_versioning")
        bname = "superduper-and-magic"
        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        p = self.load_policy(
            {
                "name": "s3-version",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": ["toggle-versioning"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)

        # eventual consistency fun for recording
        # time.sleep(10)
        versioning = client.get_bucket_versioning(Bucket=bname)["Status"]
        self.assertEqual("Enabled", versioning)

        # running against a bucket with versioning already on
        # is idempotent
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "s3-version",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "toggle-versioning", "enabled": False}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        # eventual consistency fun for recording
        # time.sleep(10)
        versioning = client.get_bucket_versioning(Bucket=bname)["Status"]
        self.assertEqual("Suspended", versioning)

    @functional
    def test_enable_logging(self):
        bname = "superduper-and-magic"

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        # only augment with logging info to minimize API calls
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_logging", "Logging", None, "LoggingEnabled")],
        )
        # and ignore any other buckets we might have in this test account
        # to minimize the placebo data and API calls
        self.patch(
            s3.S3.resource_type,
            "enum_spec",
            ('list_buckets', "Buckets[?Name=='{}']".format(bname), None)
        )
        session_factory = self.replay_flight_data("test_s3_enable_logging")

        session = session_factory()
        account_name = get_account_alias_from_sts(session)
        client = session.client("s3")
        client.create_bucket(Bucket=bname, ACL="log-delivery-write")
        self.addCleanup(destroyBucket, client, bname)

        if self.recording:
            time.sleep(5)

        acl = client.get_bucket_acl(Bucket=bname)
        self.assertEqual(len(acl['Grants']), 3)

        p = self.load_policy(
            {
                "name": "s3-version",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {
                        "type": "toggle-logging",
                        "target_bucket": bname,
                        "target_prefix": "{account}/{source_bucket_region}/{source_bucket_name}/",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)
        self.assertEqual(
            resources[0]["Logging"]["TargetPrefix"],
            "{}/{}/{}/".format(account_name, client.meta.region_name, bname)
        )

        if self.recording:
            time.sleep(5)

        logging = client.get_bucket_logging(Bucket=bname).get("LoggingEnabled")
        self.assertEqual(
            logging["TargetPrefix"], "{}/{}".format(account_name, bname)
        )

        # now override existing setting
        p = self.load_policy(
            {
                "name": "s3-version",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "bucket-logging",
                        "op": "not-equal",
                        "target_bucket": bname,
                        "target_prefix": "{account_id}/{source_bucket_name}/",
                    }
                ],
                "actions": [
                    {
                        "type": "toggle-logging",
                        "target_bucket": bname,
                        "target_prefix": "{account_id}/{source_bucket_name}/",
                    }
                ],
            },
            config={'account_id': self.account_id},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)
        self.assertEqual(
            resources[0]["Logging"]["TargetPrefix"], "{}/{}/".format(self.account_id, bname)
        )

        if self.recording:
            time.sleep(5)

        logging = client.get_bucket_logging(Bucket=bname).get("LoggingEnabled")
        self.assertTrue(logging)
        self.assertEqual(
            logging["TargetPrefix"], "{}/{}/".format(self.account_id, bname)
        )

        # Flip the switch
        p = self.load_policy(
            {
                "name": "s3-version",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "toggle-logging", "enabled": False}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], bname)

        if self.recording:
            time.sleep(20)

        logging = client.get_bucket_logging(Bucket=bname).get("LoggingEnabled")
        self.assertFalse(logging)

    def test_encrypt_policy(self):
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        session_factory = self.replay_flight_data("test_s3_encrypt_policy")
        bname = "custodian-encrypt-test"

        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        p = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": ["encryption-policy"],
            },
            session_factory=session_factory,
        )
        p.run()
        try:
            resource = session.resource("s3")
            key = resource.Object(bname, "home.txt")
            key.put(Body="hello", ContentLength=5, ContentType="text/plain")
        except ClientError as e:
            self.assertEqual(e.response["Error"]["Code"], "AccessDenied")
        else:
            self.fail("Encryption required policy")

    def test_remove_policy_none_extant(self):
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_s3_remove_empty_policy")
        bname = "custodian-policy-test"
        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        p = self.load_policy(
            {
                "name": "remove-policy",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {"type": "set-statements", "remove": ["Zebra", "Moon"]}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(ClientError, client.get_bucket_policy, Bucket=bname)

    def test_remove_policy(self):
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.RemovePolicyStatement, "executor_factory", MainThreadExecutor)

        session_factory = self.replay_flight_data("test_s3_remove_policy")
        bname = "custodian-policy-test"
        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        client.put_bucket_policy(
            Bucket=bname,
            Policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "Zebra",
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:PutObject",
                            "Resource": "arn:aws:s3:::%s/*" % bname,
                            "Condition": {
                                "StringNotEquals": {
                                    "s3:x-amz-server-side-encryption": [
                                        "AES256", "aws:kms"
                                    ]
                                }
                            },
                        }
                    ],
                }
            ),
        )
        self.addCleanup(destroyBucket, client, bname)
        p = self.load_policy(
            {
                "name": "remove-policy",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {"type": "set-statements", "remove": ["Zebra", "Moon"]}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(ClientError, client.get_bucket_policy, Bucket=bname)

    def test_remove_policy_matched(self):
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.RemovePolicyStatement, "executor_factory", MainThreadExecutor)
        self.patch(MainThreadExecutor, "c7n_async", False)

        bname = "custodian-policy-test"
        statement = {
            "Sid": "Zebra",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:PutObject",
            "Resource": "arn:aws:s3:::%s/*" % bname,
            "Condition": {
                "StringNotEquals": {
                    "s3:x-amz-server-side-encryption": ["AES256", "aws:kms"]
                }
            },
        }

        process_buckets = s3.RemovePolicyStatement.process

        def enrich(self, buckets):
            buckets[0]["CrossAccountViolations"] = [statement]
            process_buckets(self, buckets)

        self.patch(s3.RemovePolicyStatement, "process", enrich)

        session_factory = self.replay_flight_data("test_s3_remove_policy")
        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        client.put_bucket_policy(
            Bucket=bname,
            Policy=json.dumps({"Version": "2012-10-17", "Statement": [statement]}),
        )
        self.addCleanup(destroyBucket, client, bname)
        p = self.load_policy(
            {
                "name": "remove-policy",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "set-statements", "remove": "matched"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(ClientError, client.get_bucket_policy, Bucket=bname)

    def test_attach_encrypt_requires_role(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "attach-encrypt",
                "resource": "s3",
                "actions": [{"type": "attach-encrypt"}],
            },
        )

    @skip_if_not_validating
    def test_attach_encrypt_accepts_topic(self):
        p = self.load_policy(
            {
                "name": "attach-encrypt",
                "resource": "s3",
                "actions": [
                    {"type": "attach-encrypt", "role": "-", "topic": "default"}
                ],
            }
        )
        self.assertEqual(p.data["actions"][0]["topic"], "default")

    def test_create_bucket_event(self):
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_policy", "Policy", None, "Policy")]
        )
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_s3_create")
        bname = "custodian-create-bucket-v4"
        session = session_factory()
        client = session.client("s3")

        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        p = self.load_policy(
            {
                "name": "bucket-create-v2",
                "resource": "s3",
                "mode": {
                    "type": "cloudtrail",
                    "role": "arn:aws:iam::619193117841:role/CustodianDemoRole",
                    "events": ["CreateBucket"],
                },
                "actions": ["encryption-policy"],
            },
            session_factory=session_factory,
        )
        p.push(event_data("event-cloud-trail-create-bucket.json"), None)

        try:
            result = client.get_bucket_policy(Bucket=bname)
        except Exception:
            self.fail("Could not get bucket policy")

        self.assertTrue("Policy" in result)
        policy = json.loads(result["Policy"])
        self.assertEqual(
            policy,
            {
                u"Statement": [
                    {
                        u"Action": u"s3:PutObject",
                        u"Condition": {
                            u"StringNotEquals": {
                                u"s3:x-amz-server-side-encryption": [
                                    u"AES256", u"aws:kms"
                                ]
                            }
                        },
                        u"Effect": u"Deny",
                        u"Principal": u"*",
                        u"Resource": u"arn:aws:s3:::custodian-create-bucket-v4/*",
                        u"Sid": u"RequireEncryptedPutObject",
                    }
                ],
                u"Version": u"2012-10-17",
            },
        )

    def test_attach_encrypt_via_bucket_notification(self):
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_location", "Location", None, None)]
        )
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_s3_attach_encrypt_via_bucket_notification"
        )
        bname = "custodian-attach-encrypt-test"
        role = "arn:aws:iam::644160558196:role/custodian-mu"
        self.maxDiff = None
        session = session_factory(region="us-west-2")
        client = session.client("s3")
        client.create_bucket(
            Bucket=bname, CreateBucketConfiguration={"LocationConstraint": "us-west-2"}
        )
        self.addCleanup(destroyBucket, client, bname)

        p = self.load_policy(
            {
                "name": "attach-encrypt",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "attach-encrypt", "role": role}],
            },
            config=dict(region="us-west-2"),
            session_factory=session_factory,
        )

        self.addCleanup(
            LambdaManager(
                functools.partial(session_factory, region="us-west-2")
            ).remove,
            s3crypt.get_function(None, role),
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        # time.sleep(10)
        notifications = client.get_bucket_notification_configuration(Bucket=bname)
        notifications.pop("ResponseMetadata")
        self.assertEqual(
            notifications,
            {
                "LambdaFunctionConfigurations": [
                    {
                        "Events": ["s3:ObjectCreated:*"],
                        "Id": "c7n-s3-encrypt",
                        "LambdaFunctionArn": (
                            "arn:aws:lambda:us-west-2:644160558196:function:c7n-s3-encrypt"
                        ),
                    }
                ]
            },
        )
        client.put_object(
            Bucket=bname,
            Key="hello-world.txt",
            Body="hello world",
            ContentType="text/plain",
        )
        # time.sleep(30)
        info = client.head_object(Bucket=bname, Key="hello-world.txt")
        self.assertTrue("ServerSideEncryption" in info)

    def test_attach_encrypt_via_new_topic(self):
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_notification_configuration", "Notification", None, None)],
        )
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_s3_attach_encrypt_via_new_topic"
        )
        bname = "custodian-attach-encrypt-test"
        role = "arn:aws:iam::644160558196:role/custodian-mu"
        self.maxDiff = None
        session = session_factory(region="us-east-1")
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        p = self.load_policy(
            {
                "name": "attach-encrypt",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {"type": "attach-encrypt", "role": role, "topic": "default"}
                ],
            },
            session_factory=session_factory,
        )

        self.addCleanup(
            LambdaManager(
                functools.partial(session_factory, region="us-east-1")
            ).remove,
            s3crypt.get_function(None, role),
        )
        arn = "arn:aws:sns:us-east-1:644160558196:custodian-attach-encrypt-test"
        self.addCleanup(session.client("sns").delete_topic, TopicArn=arn)
        self.addCleanup(
            session.client("logs").delete_log_group,
            logGroupName="/aws/lambda/c7n-s3-encrypt",
        )

        # Check that the policy sets stuff up properly.
        resources = p.run()
        self.assertEqual(len(resources), 1)
        # time.sleep(10)
        topic_notifications = client.get_bucket_notification_configuration(
            Bucket=bname
        ).get(
            "TopicConfigurations", []
        )
        us = [t for t in topic_notifications if t.get("TopicArn") == arn]
        self.assertEqual(len(us), 1)

        # Check that the stuff behaves properly.
        client.put_object(
            Bucket=bname,
            Key="hello-world.txt",
            Body="hello world",
            ContentType="text/plain",
        )
        # time.sleep(30)
        info = client.head_object(Bucket=bname, Key="hello-world.txt")
        self.assertTrue("ServerSideEncryption" in info)

    def test_attach_encrypt_via_implicit_existing_topic(self):
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_notification_configuration", "Notification", None, None)],
        )
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_s3_attach_encrypt_via_implicit_existing_topic"
        )
        bname = "custodian-attach-encrypt-test"
        role = "arn:aws:iam::644160558196:role/custodian-mu"
        self.maxDiff = None
        session = session_factory(region="us-east-1")
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        # Create two sns topics
        topic_configs = []
        for suffix in (".jpg", ".txt"):
            sns = session.client("sns")
            existing_topic_arn = sns.create_topic(
                Name="existing-{}-{}".format(bname, suffix[1:])
            )[
                "TopicArn"
            ]
            policy = {
                "Statement": [
                    {
                        "Action": "SNS:Publish",
                        "Effect": "Allow",
                        "Resource": existing_topic_arn,
                        "Principal": {"Service": "s3.amazonaws.com"},
                    }
                ]
            }
            sns.set_topic_attributes(
                TopicArn=existing_topic_arn,
                AttributeName="Policy",
                AttributeValue=json.dumps(policy),
            )
            self.addCleanup(
                session.client("sns").delete_topic, TopicArn=existing_topic_arn
            )
            topic_configs.append(
                {
                    "TopicArn": existing_topic_arn,
                    "Events": ["s3:ObjectCreated:*"],
                    "Filter": {
                        "Key": {"FilterRules": [{"Name": "suffix", "Value": suffix}]}
                    },
                }
            )
        session.resource("s3").BucketNotification(bname).put(
            NotificationConfiguration={"TopicConfigurations": topic_configs}
        )

        # Now define the policy.
        p = self.load_policy(
            {
                "name": "attach-encrypt",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {"type": "attach-encrypt", "role": role, "topic": "default"}
                ],
            },
            session_factory=session_factory,
        )
        self.addCleanup(
            LambdaManager(
                functools.partial(session_factory, region="us-east-1")
            ).remove,
            s3crypt.get_function(None, role),
        )
        self.addCleanup(
            session.client("logs").delete_log_group,
            logGroupName="/aws/lambda/c7n-s3-encrypt",
        )

        # Check that the policy sets stuff up properly.
        resources = p.run()
        self.assertEqual(len(resources), 1)
        # time.sleep(10)
        notifies = client.get_bucket_notification_configuration(Bucket=bname).get(
            "TopicConfigurations", []
        )
        existing = [t for t in notifies if "existing" in t["TopicArn"]]
        self.assertEqual(len(existing), 2)

        # Check that the stuff behaves properly.
        client.put_object(
            Bucket=bname,
            Key="hello-world.txt",
            Body="hello world",
            ContentType="text/plain",
        )
        # time.sleep(30)
        info = client.head_object(Bucket=bname, Key="hello-world.txt")
        self.assertTrue("ServerSideEncryption" in info)

    def test_attach_encrypt_via_explicit_existing_topic(self):
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_notification_configuration", "Notification", None, None)],
        )
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_s3_attach_encrypt_via_explicit_existing_topic"
        )
        bname = "custodian-attach-encrypt-test"
        role = "arn:aws:iam::644160558196:role/custodian-mu"
        self.maxDiff = None
        session = session_factory(region="us-east-1")
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        # Create an sns topic
        topic_configs = []
        sns = session.client("sns")
        existing_topic_arn = sns.create_topic(Name="preexisting-{}".format(bname))[
            "TopicArn"
        ]
        policy = {
            "Statement": [
                {
                    "Action": "SNS:Publish",
                    "Effect": "Allow",
                    "Resource": existing_topic_arn,
                    "Principal": {"Service": "s3.amazonaws.com"},
                }
            ]
        }
        sns.set_topic_attributes(
            TopicArn=existing_topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(policy),
        )
        self.addCleanup(session.client("sns").delete_topic, TopicArn=existing_topic_arn)
        topic_configs.append(
            {"TopicArn": existing_topic_arn, "Events": ["s3:ObjectCreated:*"]}
        )
        session.resource("s3").BucketNotification(bname).put(
            NotificationConfiguration={"TopicConfigurations": topic_configs}
        )

        # Now define the policy.
        p = self.load_policy(
            {
                "name": "attach-encrypt",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {
                        "type": "attach-encrypt",
                        "role": role,
                        "topic": existing_topic_arn,
                    }
                ],
            },
            session_factory=session_factory,
        )
        self.addCleanup(
            LambdaManager(
                functools.partial(session_factory, region="us-east-1")
            ).remove,
            s3crypt.get_function(None, role),
        )
        self.addCleanup(
            session.client("logs").delete_log_group,
            logGroupName="/aws/lambda/c7n-s3-encrypt",
        )

        # Check that the policy sets stuff up properly.
        resources = p.run()
        self.assertEqual(len(resources), 1)
        # time.sleep(10)
        notifies = client.get_bucket_notification_configuration(Bucket=bname).get(
            "TopicConfigurations", []
        )
        existing = [t for t in notifies if "existing" in t["TopicArn"]]
        self.assertEqual(len(existing), 1)

        # Check that the stuff behaves properly.
        client.put_object(
            Bucket=bname,
            Key="hello-world.txt",
            Body="hello world",
            ContentType="text/plain",
        )
        # time.sleep(30)
        info = client.head_object(Bucket=bname, Key="hello-world.txt")
        self.assertTrue("ServerSideEncryption" in info)

    def test_encrypt_versioned_bucket(self):
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_versioning", "Versioning", None, None)],
        )

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.EncryptExtantKeys, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_s3_encrypt_versioned")
        bname = "custodian-encrypt-test"

        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        client.put_bucket_versioning(
            Bucket=bname, VersioningConfiguration={"Status": "Enabled"}
        )
        self.addCleanup(destroyVersionedBucket, client, bname)
        generateBucketContents(session.resource("s3"), bname)

        p = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": ["encrypt-keys"],
            },
            output_dir=None,
            session_factory=session_factory,
        )
        p.run()
        self.assertTrue(len(client.list_object_versions(Bucket=bname)["Versions"]) == 3)
        self.assertTrue(
            "ServerSideEncryption" in client.head_object(Bucket=bname, Key="home.txt")
        )

    @functional
    def test_encrypt_versioned_bucket_with_existing_keys(self):
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_versioning", "Versioning", None, None)],
        )

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.EncryptExtantKeys, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_s3_encrypt_versioned_bucket_with_existing_keys"
        )
        bname = "custodian-encrypt-test-versioning"

        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        generateBucketContents(
            session.resource("s3"), bname, {"data1.txt": "one", "data2.txt": "two"}
        )
        client.put_bucket_versioning(
            Bucket=bname, VersioningConfiguration={"Status": "Enabled"}
        )
        self.addCleanup(destroyVersionedBucket, client, bname)
        generateBucketContents(session.resource("s3"), bname, {"data1.txt": "three"})

        p = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": ["encrypt-keys"],
            },
            output_dir=None,
            session_factory=session_factory,
        )
        p.run()

        self.assertTrue(len(client.list_object_versions(Bucket=bname)["Versions"]) == 2)
        self.assertTrue(
            "ServerSideEncryption" in client.head_object(Bucket=bname, Key="data1.txt")
        )
        self.assertTrue(
            "ServerSideEncryption" in client.head_object(Bucket=bname, Key="data2.txt")
        )

    def test_encrypt_key_empty_bucket(self):
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        self.patch(s3.EncryptExtantKeys, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_s3_encrypt_empty")
        bname = "custodian-encrypt-test"

        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        p = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": ["encrypt-keys"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_encrypt_keys(self):
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_encrypt")
        bname = "custodian-encrypt-test"

        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        generateBucketContents(session.resource("s3"), bname)

        # start with a report-only option since it doesn't modify the bucket
        report_policy = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "encrypt-keys", "report-only": True}],
            },
            output_dir=None,
            session_factory=session_factory,
        )
        report_resources = report_policy.run()

        self.assertEqual(report_resources[0]["KeyRemediated"], 3)

        p = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": ["encrypt-keys"],
            },
            output_dir=None,
            session_factory=session_factory,
        )
        p.run()

        self.assertTrue(
            "ServerSideEncryption" in client.head_object(Bucket=bname, Key="home.txt")
        )

        # re-run the report policy after to ensure we have no items
        # needing remediation
        report_resources = report_policy.run()
        self.assertEqual(report_resources[0]["KeyRemediated"], 0)

    def test_encrypt_keys_aes256_sufficient(self):
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_encrypt_aes256_sufficient")
        bname = "custodian-encrypt-sufficient-test"

        session = session_factory()
        client = session.client("s3")
        kms = session.client("kms")

        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        key_id = [
            k
            for k in kms.list_aliases().get("Aliases", ())
            if k["AliasName"] == "alias/aws/s3"
        ][
            0
        ][
            "AliasArn"
        ]

        client.put_object(
            Bucket=bname,
            Key="testing-abc",
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=key_id,
        )
        client.put_object(
            Bucket=bname, Key="testing-123", ServerSideEncryption="AES256"
        )

        p = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "encrypt-keys"}],
            },
            output_dir=None,
            session_factory=session_factory,
        )

        p.run()

        result = client.head_object(Bucket=bname, Key="testing-123")
        self.assertTrue(result["ServerSideEncryption"] == "AES256")

        result = client.head_object(Bucket=bname, Key="testing-abc")
        self.assertTrue(result["ServerSideEncryption"] == "aws:kms")
        data = json.load(
            open(os.path.join(p.ctx.output.root_dir, "action-encryptextantkeys"))
        )
        self.assertEqual([{"Count": 2, "Remediated": 0, "Bucket": bname}], data)

    def test_encrypt_keys_key_id_option(self):
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_encrypt_key_id_option")
        bname = "custodian-encrypt-test"

        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        generateBucketContents(session.resource("s3"), bname)

        key_one = "845ab6f1-744c-4edc-b702-efae6836818a"
        p = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {"type": "encrypt-keys", "crypto": "aws:kms", "key-id": key_one}
                ],
            },
            output_dir=None,
            session_factory=session_factory,
        )
        p.run()
        result = client.head_object(Bucket=bname, Key="home.txt")
        self.assertTrue("SSEKMSKeyId" in result)
        self.assertTrue(key_one in result["SSEKMSKeyId"])

        # Now test that we can re-key it to something else
        key_two = "5fd9f6d6-4294-4926-8719-1e85695e2ad6"
        p = self.load_policy(
            {
                "name": "encrypt-keys",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {"type": "encrypt-keys", "crypto": "aws:kms", "key-id": key_two}
                ],
            },
            output_dir=None,
            session_factory=session_factory,
        )
        p.run()
        result = client.head_object(Bucket=bname, Key="home.txt")
        self.assertTrue("SSEKMSKeyId" in result)
        self.assertTrue(key_two in result["SSEKMSKeyId"])

    def test_global_grants_filter_option(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [("get_bucket_acl", "Acl", None, None)])
        session_factory = self.replay_flight_data("test_s3_global_grants_filter")
        bname = "custodian-testing-grants"
        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        public = "http://acs.amazonaws.com/groups/global/AllUsers"

        client.put_bucket_acl(
            Bucket=bname,
            AccessControlPolicy={
                "Owner": {
                    "DisplayName": "k_vertigo",
                    "ID": "904fc4c4790937100e9eb293a15e6a0a1f265a064888055b43d030034f8881ee",
                },
                "Grants": [
                    {"Grantee": {"Type": "Group", "URI": public}, "Permission": "WRITE"}
                ],
            },
        )
        p = self.load_policy(
            {
                "name": "s3-global-check",
                "resource": "s3",
                "filters": [
                    {"Name": "custodian-testing-grants"},
                    {"type": "global-grants", "permissions": ["READ_ACP"]},
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

        p = self.load_policy(
            {
                "name": "s3-global-check",
                "resource": "s3",
                "filters": [
                    {"Name": "custodian-testing-grants"},
                    {"type": "global-grants", "permissions": ["WRITE"]},
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_global_grants_filter_and_remove(self):
        self.patch(s3, "S3_AUGMENT_TABLE", [("get_bucket_acl", "Acl", None, None)])
        session_factory = self.replay_flight_data("test_s3_grants")

        bname = "custodian-testing-grants"
        session = session_factory()
        client = session.client("s3")
        client.create_bucket(Bucket=bname)

        public = "http://acs.amazonaws.com/groups/global/AllUsers"
        client.put_bucket_acl(
            Bucket=bname,
            AccessControlPolicy={
                "Owner": {
                    "DisplayName": "k_vertigo",
                    "ID": "904fc4c4790937100e9eb293a15e6a0a1f265a064888055b43d030034f8881ee",
                },
                "Grants": [
                    {"Grantee": {"Type": "Group", "URI": public}, "Permission": "WRITE"}
                ],
            },
        )
        p = self.load_policy(
            {
                "name": "s3-remove-global",
                "resource": "s3",
                "filters": [
                    {"Name": "custodian-testing-grants"}, {"type": "global-grants"}
                ],
                "actions": [{"type": "delete-global-grants", "grantees": [public]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        grants = client.get_bucket_acl(Bucket=bname)
        client.delete_bucket(Bucket=bname)
        self.assertEqual(grants["Grants"], [])
        self.assertEqual(resources[0]["Name"], bname)

    def test_s3_mark_for_op(self):
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_tagging", "Tags", [], "TagSet")]
        )
        session_factory = self.replay_flight_data("test_s3_mark_for_op")
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-mark-test"
        p = self.load_policy(
            {
                "name": "s3-mark",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "mark-for-op", "days": 3, "op": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.get_bucket_tagging(Bucket=bname)
        tag_map = {t["Key"]: t["Value"] for t in tags.get("TagSet", {})}
        self.assertTrue("maid_status" in tag_map)
        self.assertTrue("delete" in tag_map.get("maid_status"))

    def test_s3_remove_tag(self):
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_tagging", "Tags", [], "TagSet")]
        )
        self.patch(s3.RemoveTag, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_s3_remove_tag")
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-mark-test"
        p = self.load_policy(
            {
                "name": "s3-unmark",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": ["unmark"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.get_bucket_tagging(Bucket=bname)
        tag_map = {t["Key"]: t["Value"] for t in tags.get("TagSet", {})}
        self.assertTrue("maid_status" not in tag_map)
        old_tags = {t["Key"]: t["Value"] for t in resources[0]["Tags"]}
        self.assertTrue("maid_status" in old_tags)

    def test_hosts_website(self):
        self.patch(
            s3, "S3_AUGMENT_TABLE", [("get_bucket_website", "Website", None, None)]
        )
        session_factory = self.replay_flight_data("test_s3_hosts_website")
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-static-website-test"
        client.create_bucket(Bucket=bname)
        client.put_bucket_website(
            Bucket=bname,
            WebsiteConfiguration={
                "ErrorDocument": {"Key": "error.html"},
                "IndexDocument": {"Suffix": "index.html"},
            },
        )
        self.addCleanup(client.delete_bucket, Bucket=bname)
        p = self.load_policy(
            {
                "name": "s3-website-hosting",
                "resource": "s3",
                "filters": [{"Website": "not-null"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        names = [b["Name"] for b in resources]
        self.assertTrue(bname in names)

        p = self.load_policy(
            {
                "name": "s3-website-hosting",
                "resource": "s3",
                "filters": [{"Website": "not-null"}],
                "actions": ["remove-website-hosting"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_delete_bucket_notification(self):
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_notification_configuration", "Notification", None, None)],
        )
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_s3_delete_bucket_notification")
        bname = "custodian-delete-bucket-notification-test"
        config_id = "c7n-notify-1"
        self.maxDiff = None
        session = session_factory(region="us-east-1")
        client = session.client("s3")
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        p = self.load_policy(
            {
                "name": "s3-delete-bucket-notification",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "bucket-notification",
                        "kind": "sns",
                        "key": "Id",
                        "value": config_id,
                        "op": "eq",
                    },
                ],
                "actions": [
                    {"type": "delete-bucket-notification", "statement_ids": "matched"}
                ],
            },
            session_factory=session_factory,
        )

        topic_arn = session.client("sns").create_topic(Name="bucket-notification-test")[
            "TopicArn"
        ]
        self.addCleanup(session.client("sns").delete_topic, TopicArn=topic_arn)
        topic_policy = {
            "Statement": [
                {
                    "Action": "SNS:Publish",
                    "Effect": "Allow",
                    "Resource": topic_arn,
                    "Principal": {"Service": "s3.amazonaws.com"},
                }
            ]
        }
        session.client("sns").set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(topic_policy),
        )
        client.put_bucket_notification_configuration(
            Bucket=bname,
            NotificationConfiguration={
                "TopicConfigurations": [
                    {
                        "TopicArn": topic_arn,
                        "Events": ["s3:ObjectCreated:*"],
                        "Id": config_id,
                    },
                    {
                        "TopicArn": topic_arn,
                        "Events": ["s3:ObjectRemoved:*"],
                        "Id": "another1",
                    },
                ]
            },
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        # time.sleep(10)
        topic_notifications = client.get_bucket_notification_configuration(
            Bucket=bname
        ).get(
            "TopicConfigurations", []
        )
        us = [t for t in topic_notifications if t.get("TopicArn") == topic_arn]
        self.assertEqual(len(us), 1)

    def test_enable_bucket_encryption_kms(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data(
            "test_s3_enable_bucket_encryption_kms"
        )
        session = session_factory()
        client = session.client("s3")
        kms_client = session.client("kms")
        bname = "custodian-enable-bucket-encryption-kms"

        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        with self.assertRaises(Exception):
            response = client.get_bucket_encryption(Bucket=bname)

        key = kms_client.list_keys()["Keys"][0]
        key_arn = kms_client.describe_key(KeyId=key["KeyId"])["KeyMetadata"]["Arn"]
        p = self.load_policy(
            {
                "name": "s3-enable-bucket-encryption",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {
                        "type": "set-bucket-encryption",
                        "key": str(key["KeyId"]),
                        "crypto": "aws:kms",
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(5)

        response = client.get_bucket_encryption(Bucket=bname)
        rules = response["ServerSideEncryptionConfiguration"]["Rules"][0][
            "ApplyServerSideEncryptionByDefault"
        ]
        self.assertEqual(rules["SSEAlgorithm"], "aws:kms")
        self.assertEqual(rules["KMSMasterKeyID"], key_arn)

    def test_enable_bucket_encryption_kms_alias(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data(
            "test_s3_enable_bucket_encryption_kms_alias"
        )
        session = session_factory()
        client = session.client("s3")
        kms_client = session.client("kms")
        bname = "custodian-enable-bucket-encryption-kms-alias"
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        kms_alias = "alias/some-key"
        kms_alias_id = kms_client.describe_key(KeyId=kms_alias)["KeyMetadata"]["Arn"]
        p = self.load_policy(
            {
                "name": "s3-enable-bucket-encryption-alias",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {
                        "type": "set-bucket-encryption",
                        "crypto": "aws:kms",
                        "key": kms_alias,
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(5)

        response = client.get_bucket_encryption(Bucket=bname)
        rules = response["ServerSideEncryptionConfiguration"]["Rules"][0][
            "ApplyServerSideEncryptionByDefault"
        ]
        self.assertEqual(rules["SSEAlgorithm"], "aws:kms")
        self.assertEqual(rules["KMSMasterKeyID"], kms_alias_id)

        bname = "custodian-enable-bucket-encryption-kms-bad-alias"
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        p = self.load_policy(
            {
                "name": "s3-enable-bucket-encryption-bad-alias",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [
                    {
                        "type": "set-bucket-encryption",
                        "crypto": "aws:kms",
                        "key": "alias/some-nonexistant-alias",
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(5)

        with self.assertRaises(ClientError):
            client.get_bucket_encryption(Bucket=bname)

    def test_enable_bucket_encryption_aes256(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data(
            "test_s3_enable_bucket_encryption_aes256"
        )
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-enable-bucket-encryption-aes256"

        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        with self.assertRaises(Exception):
            client.get_bucket_encryption(Bucket=bname)

        p = self.load_policy(
            {
                "name": "s3-enable-bucket-encryption",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "set-bucket-encryption"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)

        response = client.get_bucket_encryption(Bucket=bname)
        rules = response["ServerSideEncryptionConfiguration"]["Rules"][0][
            "ApplyServerSideEncryptionByDefault"
        ]
        self.assertEqual(rules["SSEAlgorithm"], "AES256")

        client.delete_bucket_encryption(Bucket=bname)
        if self.recording:
            time.sleep(5)

        with self.assertRaises(Exception):
            client.get_bucket_encryption(Bucket=bname)

        p = self.load_policy(
            {
                "name": "s3-enable-bucket-encryption",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "set-bucket-encryption", "crypto": "AES256"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)

        response = client.get_bucket_encryption(Bucket=bname)
        rules = response["ServerSideEncryptionConfiguration"]["Rules"][0][
            "ApplyServerSideEncryptionByDefault"
        ]
        self.assertEqual(rules["SSEAlgorithm"], "AES256")

    def test_delete_bucket_encryption(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_delete_bucket_encryption")
        session = session_factory()
        client = session.client("s3")
        bname = "custodian-delete-bucket-encryption-aes256"

        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        with self.assertRaises(Exception):
            client.get_bucket_encryption(Bucket=bname)

        client.put_bucket_encryption(
            Bucket=bname,
            ServerSideEncryptionConfiguration={
                "Rules": [
                    {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
        )

        p = self.load_policy(
            {
                "name": "s3-delete-bucket-encryption",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "set-bucket-encryption", "enabled": False}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)
        with self.assertRaises(Exception):
            client.get_bucket_encryption(Bucket=bname)

    @mock.patch('c7n.actions.invoke.assumed_session')
    def test_s3_invoke_lambda_assume_role_action(self, mock_assumed_session):

        session_factory = self.replay_flight_data("test_s3_invoke_lambda_assume_role")

        p = self.load_policy(
            {
                "name": "s3-invoke-lambda-assume-role",
                "resource": "s3",
                "actions": [{"type": "invoke-lambda",
                             "function": "lambda-invoke-with-assume-role", "assume-role":
                                 "arn:aws:iam::0123456789:role/service-role/lambda-assumed-role"}],
            },
            session_factory=session_factory,
        )

        p.resource_manager.actions[0].process([{
            "FunctionName": "abc",
            "payload": {},
        }])

        assert mock_assumed_session.call_count == 1

    def test_s3_data_events(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_data_events")

        p = self.load_policy(
            {
                "name": "s3-data-events",
                "resource": "s3",
                "filters": [{"type": "data-events"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        assert {bucket["Name"] for bucket in resources} == {"bucket-with-data-events"}

    def test_s3_dataaccesspointaccount_cross_account(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_s3_dataaccesspointaccount_cross_account")

        p = self.load_policy(
            {
                "name": "s3-data-access-point-account-cross-account",
                "resource": "s3",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class S3LifecycleTest(BaseTest):

    def test_lifecycle(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_lifecycle_configuration", "Lifecycle", None, None)],
        )
        session_factory = self.replay_flight_data("test_s3_lifecycle")
        session = session_factory()
        client = session.client("s3")
        bname = "c7n-lifecycle-test-again3"

        # Make a bucket
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)
        buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}
        self.assertIn(bname, buckets)

        def get_policy(**kwargs):
            rule = {
                "Status": "Enabled",
                "Filter": {"Prefix": "foo/"},
                "Transitions": [{"Days": 60, "StorageClass": "GLACIER"}],
            }
            rule.update(**kwargs)

            policy = {
                "name": "s3-lifecycle",
                "resource": "s3",
                "filters": [{"Name": bname}],
                "actions": [{"type": "configure-lifecycle", "rules": [rule]}],
            }
            return policy

        def run_policy(policy):
            p = self.load_policy(policy, session_factory=session_factory)
            resources = p.run()
            self.assertEqual(len(resources), 1)

            if self.recording:
                time.sleep(5)

        #
        # Add the first lifecycle
        #
        lifecycle_id1 = "test-lifecycle"
        policy = get_policy(ID=lifecycle_id1)
        run_policy(policy)
        lifecycle = client.get_bucket_lifecycle_configuration(Bucket=bname)
        self.assertEqual(lifecycle["Rules"][0]["ID"], lifecycle_id1)

        #
        # Now add another lifecycle rule to ensure it doesn't clobber the first one
        #
        lifecycle_id2 = "test-lifecycle-two"
        policy = get_policy(ID=lifecycle_id2, Filter={"Prefix": "bar/"})
        run_policy(policy)

        # Verify the lifecycle
        lifecycle = client.get_bucket_lifecycle_configuration(Bucket=bname)
        self.assertEqual(len(lifecycle["Rules"]), 2)
        self.assertSetEqual(
            {x["ID"] for x in lifecycle["Rules"]},
            {lifecycle_id1, lifecycle_id2},
        )

        #
        # Next, overwrite one of the lifecycles and make sure it changed
        #
        policy = get_policy(ID=lifecycle_id2, Filter={"Prefix": "baz/"})
        run_policy(policy)

        # Verify the lifecycle
        lifecycle = client.get_bucket_lifecycle_configuration(Bucket=bname)
        self.assertEqual(len(lifecycle["Rules"]), 2)
        self.assertSetEqual(
            {x["ID"] for x in lifecycle["Rules"]},
            {lifecycle_id1, lifecycle_id2},
        )

        for rule in lifecycle["Rules"]:
            if rule["ID"] == lifecycle_id2:
                self.assertEqual(rule["Filter"]["Prefix"], "baz/")

        #
        # Test deleting a lifecycle
        #
        policy = get_policy(ID=lifecycle_id1, Status="absent")
        run_policy(policy)

        lifecycle = client.get_bucket_lifecycle_configuration(Bucket=bname)
        self.assertEqual(len(lifecycle["Rules"]), 1)
        self.assertEqual(lifecycle["Rules"][0]["ID"], lifecycle_id2)

    def test_s3_remove_lifecycle_rule_id(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(
            s3,
            "S3_AUGMENT_TABLE",
            [("get_bucket_lifecycle_configuration", "Lifecycle", None, None)],)
        bname = 'c7n-test-1'
        session_factory = self.replay_flight_data("test_s3_remove_lifecycle_rule_id")
        session = session_factory()
        client = session.client("s3")
        lifecycle = client.get_bucket_lifecycle_configuration(Bucket=bname)
        self.assertSetEqual(
            {x["ID"] for x in lifecycle["Rules"]},
            {'id2'},)
        p = self.load_policy(
            {
                "name": "s3-remove-lc-rule-id",
                "resource": "s3",
                "filters": [
                    {
                        "Name": bname
                    }
                ],
                "actions": [
                    {
                        "type": "configure-lifecycle",
                        "rules": [
                            {
                                "ID": "id2",
                                "Status": "absent",
                            },
                            {
                                "ID": "id1",
                                "Status": "absent",
                            },
                        ]
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        with self.assertRaises(Exception):
            client.get_bucket_lifecycle_configuration(Bucket=bname)


@terraform('aws_s3_encryption_audit')
def test_s3_encryption_audit(test, aws_s3_encryption_audit):
    test.patch(s3.S3, "executor_factory", MainThreadExecutor)
    test.patch(s3.BucketEncryption, "executor_factory", MainThreadExecutor)
    test.patch(s3, "S3_AUGMENT_TABLE", [])
    session_factory = test.replay_flight_data("test_s3_encryption_audit")

    p = test.load_policy(
        {
            "name": "s3-audit",
            "resource": "s3",
            "filters": [
                {"type": "value",
                 "key": "Name",
                 "op": "in",
                 "value": [
                     'c7n-aws-s3-encryption-audit-test-a',
                     'c7n-aws-s3-encryption-audit-test-b',
                     'c7n-aws-s3-encryption-audit-test-c',
                 ]},
                {
                    "or": [
                        {
                            "type": "bucket-encryption",
                            "state": False,
                        },
                        {
                            "type": "bucket-encryption",
                            "crypto": "aws:kms",
                            "state": True,
                        },
                        {
                            "type": "bucket-encryption",
                            "crypto": "AES256",
                            "state": True,
                        },
                    ]
                },
            ],
        },
        session_factory=session_factory,
    )

    resources = p.run()

    assert len(resources) == 3

    expected_names = [
        'c7n-aws-s3-encryption-audit-test-a',
        'c7n-aws-s3-encryption-audit-test-b',
        'c7n-aws-s3-encryption-audit-test-c',
    ]
    actual_names = sorted([r.get('Name') for r in resources])

    assert actual_names == expected_names


# s3 changed behavior for new buckets in 2023
# https://aws.amazon.com/blogs/aws/heads-up-amazon-s3-security-changes-are-coming-in-april-of-2023/

@pytest.mark.skiplive
@terraform('s3_ownership', scope='class')
class TestBucketOwnership:
    def test_s3_ownership_empty(self, test, s3_ownership):
        test.patch(s3.S3, "executor_factory", MainThreadExecutor)
        test.patch(s3.BucketOwnershipControls, "executor_factory", MainThreadExecutor)
        test.patch(
            s3, "S3_AUGMENT_TABLE", []
        )
        session_factory = test.replay_flight_data("test_s3_ownership_empty")
        bucket_name = s3_ownership['aws_s3_bucket.no_ownership_controls.bucket']
        p = test.load_policy(
            {
                "name": "s3-ownership-empty",
                "resource": "s3",
                "filters": [
                    {"type": "value",
                     "op": "glob",
                     "key": "Name",
                     "value": "c7ntest*"},
                    {"type": "ownership",
                     "value": "empty"},
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]["Name"] == bucket_name

    def test_s3_ownership_defined(self, test, s3_ownership):
        test.patch(s3.S3, "executor_factory", MainThreadExecutor)
        test.patch(s3.BucketOwnershipControls, "executor_factory", MainThreadExecutor)
        test.patch(
            s3, "S3_AUGMENT_TABLE", []
        )
        session_factory = test.replay_flight_data("test_s3_ownership_defined")
        bucket_names = {s3_ownership[f'aws_s3_bucket.{r}.bucket']
                        for r in ('owner_preferred', 'owner_enforced')}
        p = test.load_policy(
            {
                "name": "s3-ownership-defined",
                "resource": "s3",
                "filters": [
                    {"type": "value",
                     "op": "glob",
                     "key": "Name",
                     "value": "c7ntest*"},
                    {"type": "ownership",
                     "op": "in",
                     "value": ["BucketOwnerPreferred", "BucketOwnerEnforced"]},
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        assert len(resources) == 2
        assert {r["Name"] for r in resources} == bucket_names

    def test_s3_access_analyzer_filter_with_no_results(self, test, s3_ownership):
        test.patch(s3.S3, "executor_factory", MainThreadExecutor)
        test.patch(s3.BucketOwnershipControls, "executor_factory", MainThreadExecutor)
        test.patch(s3, "S3_AUGMENT_TABLE", [])
        factory = test.replay_flight_data("test_s3_iam_analyzers")
        p = test.load_policy({
            'name': 'check-s3',
            'resource': 'aws.s3',
            'filters': [
                {
                    'type': 'iam-analyzer',
                    'key': 'isPublic',
                    'value': True,
                },
            ]
        }, session_factory=factory)
        test.assertRaises(PolicyExecutionError, p.run)


class IntelligentTieringConfiguration(BaseTest):

    def test_set_intelligent_configuration_validation_error(self):
        with self.assertRaises(PolicyValidationError) as e:
            self.load_policy({
                'name': 's3-apply-int-tier-config',
                'resource': 'aws.s3',
                'actions': [
                    {
                        'type': 'set-intelligent-tiering',
                        'Id': 'xyz',
                        'State': 'delete'
                    }
                ]
            })
        self.assertIn(
            "may only be used in conjunction with `intelligent-tiering`", str(e.exception))

    def test_s3_int_tiering_set_configurations(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        bname = "example-abc-123"
        session_factory = self.replay_flight_data("test_s3_int_tiering_set_configurations")
        session = session_factory()
        client = session.client("s3")
        configs = client.list_bucket_intelligent_tiering_configurations(Bucket=bname)
        filtered_config = {
            'Id': 'test-config',
            'Filter': {'And': {'Prefix': 'test', 'Tags': [{'Key': 'Owner', 'Value': 'c7n'}]}},
            'Status': 'Enabled',
            'Tierings': [
                {'Days': 100, 'AccessTier': 'ARCHIVE_ACCESS'}
            ]
        }
        applied_config = {
            'Id': 'c7n-default',
            'Filter': {
                'And': {
                    'Prefix': 'test',
                    'Tags': [
                        {'Key': 'Owner', 'Value': 'c7n'},
                        {"Key": "AnotherOnwer", "Value": "Enterprise"}]}},
            'Status': 'Enabled',
            'Tierings': [
                {'Days': 150, 'AccessTier': 'ARCHIVE_ACCESS'},
                {'Days': 200, 'AccessTier': 'DEEP_ARCHIVE_ACCESS'}
            ]
        }
        self.assertTrue(filtered_config in configs.get('IntelligentTieringConfigurationList'))
        p = self.load_policy(
            {
                "name": "s3-filter-configs-and-apply",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "intelligent-tiering",
                        "attrs": [
                          {"Status": "Enabled"},
                          {"Filter": {
                              "And": {
                                  "Prefix": "test", "Tags": [{"Key": "Owner", "Value": "c7n"}]}}},
                          {"Tierings": [{"Days": 100, "AccessTier": "ARCHIVE_ACCESS"}]}]
                    }
                ],
                "actions": [
                    {
                        "type": "set-intelligent-tiering",
                        "State": "delete",
                        "Id": "matched",
                    },
                    {
                        "type": "set-intelligent-tiering",
                        "Id": "c7n-default",
                        "IntelligentTieringConfiguration": {
                            "Id": "c7n-default",
                            "Status": "Enabled",
                            "Filter": {
                                "And": {
                                    "Prefix": "test",
                                    "Tags": [
                                        {"Key": "Owner", "Value": "c7n"},
                                        {"Key": "AnotherOnwer", "Value": "Enterprise"}]}},
                            "Tierings": [
                                {
                                    "Days": 150,
                                    "AccessTier": "ARCHIVE_ACCESS"
                                },
                                {
                                    "Days": 200,
                                    "AccessTier": "DEEP_ARCHIVE_ACCESS"
                                }
                            ]
                        }
                    }],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("c7n:IntelligentTiering" in resources[0])
        self.assertEqual(len(resources[0].get("c7n:ListItemMatches")), 1)
        self.assertEqual(resources[0].get("c7n:ListItemMatches")[0].get("Id"), "test-config")
        check_config = client.list_bucket_intelligent_tiering_configurations(Bucket=bname)
        self.assertFalse(filtered_config in check_config.get('IntelligentTieringConfigurationList'))
        self.assertTrue(applied_config in check_config.get('IntelligentTieringConfigurationList'))

    def test_s3_int_tiering_delete_configurations_id(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        bname = "example-abc-123"
        session_factory = self.replay_flight_data("test_s3_int_tiering_delete_configurations_id")
        session = session_factory()
        client = session.client("s3")
        ids = []
        configs = client.list_bucket_intelligent_tiering_configurations(
            Bucket=bname).get('IntelligentTieringConfigurationList')
        self.assertEqual(len(configs), 2)
        for config in configs:
            ids.append(jmespath_search("Id", config))
        self.assertTrue("c7n-default" in ids)
        p = self.load_policy(
            {
                "name": "s3-filter-configs-and-apply",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "intelligent-tiering",
                        "attrs": [
                          {"Status": "Enabled"},
                          {"Id": "c7n-default"}]
                    }
                ],
                "actions": [
                    {
                        "type": "set-intelligent-tiering",
                        "State": "delete",
                        "Id": "c7n-default",
                    }],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].get("c7n:ListItemMatches")[0].get("Id"), "c7n-default")
        check_config = client.list_bucket_intelligent_tiering_configurations(
            Bucket=bname).get('IntelligentTieringConfigurationList')
        self.assertEqual(len(check_config), 1)
        self.assertFalse('c7n-default' in check_config[0].get('Id'))

    def test_delete_int_tier_config_not_present(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        bname = "example-abc-123"
        session_factory = self.replay_flight_data("test_delete_int_tier_config_not_present")
        session = session_factory()
        client = session.client("s3")
        config = client.list_bucket_intelligent_tiering_configurations(
            Bucket=bname).get('IntelligentTieringConfigurationList')
        self.assertEqual(len(config), 1)
        id = config[0].get('Id')
        self.assertTrue("present" in id)
        log_output = self.capture_logging('custodian.s3', level=logging.WARNING)
        p = self.load_policy(
            {
                "name": "s3-filter-configs-and-apply",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "intelligent-tiering",
                        "attrs": [{"Status": "Enabled"}]
                    }
                ],
                "actions": [
                    {
                        "type": "set-intelligent-tiering",
                        "State": "delete",
                        "Id": "not-present",
                    }],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        check_config = client.list_bucket_intelligent_tiering_configurations(
            Bucket=bname).get('IntelligentTieringConfigurationList')
        self.assertEqual(len(check_config), 1)
        self.assertTrue('present' in check_config[0].get('Id'))
        self.assertIn(
          'No such configuration found:example-abc-123 while deleting '
          'intelligent tiering configuration',
            log_output.getvalue())

    def test_s3_intel_tier_config_access_denied(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        bname = "example-abc-123"
        session_factory = self.replay_flight_data("test_s3_intel_tier_config_access_denied")
        log_output = self.capture_logging('custodian.s3', level=logging.WARNING)
        p = self.load_policy(
            {
                "name": "s3-filter-configs-and-apply",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {"type": "intelligent-tiering"}],
                "actions": [
                    {
                        "type": "set-intelligent-tiering",
                        "State": "delete",
                        "Id": "not-present",
                    }],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn(
          'Access Denied Bucket:example-abc-123 while deleting intelligent tiering configuration',
            log_output.getvalue())

        p1 = self.load_policy(
            {
                "name": "s3-filter-configs-and-apply",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {"type": "intelligent-tiering"}],
                "actions": [
                    {
                        "type": "set-intelligent-tiering",
                        "Id": "not-present",
                        "IntelligentTieringConfiguration": {
                        "Id": "not-present",
                        "Status": "Enabled",
                        "Filter": {
                            "And": {
                                "Prefix": "test",
                                "Tags": [
                                    {"Key": "Owner", "Value": "c7n"}]}},
                            "Tierings": [{
                                    "Days": 150,
                                    "AccessTier": "ARCHIVE_ACCESS"
                                }],
                        }
                    }],
            },
            session_factory=session_factory,
        )
        resources = p1.run()
        self.assertEqual(len(resources), 1)
        self.assertIn(
          'Access Denied Bucket:example-abc-123 while applying intelligent tiering configuration',
            log_output.getvalue())

    def test_s3_intel_tier_config_filter_count(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        bname = "example-abc-123"
        session_factory = self.replay_flight_data("test_s3_intel_tier_config_filter_count")
        p = self.load_policy(
            {
                "name": "s3-filter-configs-and-apply",
                "resource": "s3",
                "filters": [
                    {"Name": bname},
                    {
                        "type": "intelligent-tiering",
                        "count": 2,
                        "count_op": "eq"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]["c7n:IntelligentTiering"]), 2)

    def test_set_intelligent_configuration_schema_validation(self):
        with self.assertRaises(PolicyValidationError) as e:
            self.load_policy({
                'name': 's3-apply-int-tier-config',
                'resource': 'aws.s3',
                'filters': [{'type': 'intelligent-tiering'}],
                'actions': [
                    {
                        'type': 'set-intelligent-tiering',
                        'Id': 'xyz',
                        'IntelligentTieringConfiguration': {
                          'Id': 'xyz',
                          'Status': 'Enabled'}
                    }
                ]
            })
        self.assertIn(
            'Missing required parameter in IntelligentTieringConfiguration: "Tierings"', str(
              e.exception))

    def test_s3_list_tiering_config_denied_method(self):
        b = {'Name': 'example-abc-123',
            'c7n:DeniedMethods': ['list_bucket_intelligent_tiering_configurations']}
        log_output = self.capture_logging('custodian.s3', level=logging.WARNING)
        p = self.load_policy({'name': 's3-apply-int-tier-config-filter',
                'resource': 'aws.s3',
                'filters': [{'type': 'intelligent-tiering'}],
                'actions': [{'type': 'set-intelligent-tiering', 'Id': 'test', 'State': 'delete'}]
            },
        )
        action_set_config = p.resource_manager.actions[0]
        self.assertEqual(action_set_config.process_bucket(b), None)
        self.assertIn(
          'Access Denied Bucket:example-abc-123 while reading intelligent tiering configurations',
            log_output.getvalue())


class BucketReplication(BaseTest):
    def test_s3_bucket_replication_filter(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        self.patch(s3, "S3_AUGMENT_TABLE", [('get_bucket_replication',
        'Replication', None, None, 's3:GetReplicationConfiguration')])
        session_factory = self.replay_flight_data("test_s3_bucket_replication_filter")
        p = self.load_policy(
            {
                "name": "s3-replication-rule",
                "resource": "s3",
                "filters": [
                        {
                            "type": "bucket-replication",
                            "attrs": [
                            {"Status": "Enabled"},
                            {"Filter": {
                                "And": {
                                    "Prefix": "abc", "Tags": [{"Key": "Owner", "Value": "c7n"}]}}},
                            {"DestinationRegion": "us-west-2"},
                            {"CrossRegion": True}
                            ]
                        }
                    ],
                },
            session_factory=session_factory,
        )
        with vcr.use_cassette(
          'tests/data/vcr_cassettes/test_s3/replication_rule.yaml',
           record_mode='none'
        ):
            resources = p.run()
            self.assertEqual(len(resources), 1)
            self.assertTrue("Replication" in resources[0])
            self.assertEqual(len(resources[0].get("c7n:ListItemMatches")), 1)

    def test_s3_bucket_replication_filter_count(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        self.patch(s3, "S3_AUGMENT_TABLE", [('get_bucket_replication',
        'Replication', None, None, 's3:GetReplicationConfiguration')])
        session_factory = self.replay_flight_data("test_s3_bucket_replication_filter_count")
        p = self.load_policy(
            {
                "name": "s3-replication-filter-count",
                "resource": "s3",
                "filters": [
                    {
                        "type": "bucket-replication",
                        "count": 1,
                        "count_op": "eq"
                    }
                ],
            },
            session_factory=session_factory,
        )
        with vcr.use_cassette(
          'tests/data/vcr_cassettes/test_s3/replication_filter_count.yaml',
           record_mode='none'
        ):
            resources = p.run()
            self.assertEqual(len(resources), 1)
            self.assertEqual(resources[0]['Name'], 'custodian-replication-test-1')

    def test_s3_bucket_no_replication_rule(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        self.patch(s3, "S3_AUGMENT_TABLE", [('get_bucket_replication',
        'Replication', None, None, 's3:GetReplicationConfiguration')])
        session_factory = self.replay_flight_data("test_s3_bucket_no_replication_rule")
        p = self.load_policy(
            {
                "name": "s3-no-replication-rule",
                "resource": "s3",
                "filters": [
                    {
                        "not": [
                            "bucket-replication"
                        ]
                    }
                ],
            },
            session_factory=session_factory,
        )
        with vcr.use_cassette(
          'tests/data/vcr_cassettes/test_s3/no_replication_rule.yaml',
           record_mode='none'
        ):
            resources = p.run()
            self.assertEqual(len(resources), 1)
            self.assertEqual(resources[0]['Name'], 'custodian-replication-west')

    def test_s3_bucket_replication_no_bucket(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        self.patch(s3, "S3_AUGMENT_TABLE", [('get_bucket_replication',
        'Replication', None, None, 's3:GetReplicationConfiguration')])
        session_factory = self.replay_flight_data("test_s3_bucket_replication_no_bucket")
        p = self.load_policy(
            {
                "name": "s3-replication-rule",
                "resource": "s3",
                "filters": [
                        {
                            "type": "bucket-replication",
                            "attrs": [
                            {"Status": "Enabled"},
                            {"DestinationBucketAvailable": False}
                            ]
                        }
                    ],
                },
            session_factory=session_factory,
        )
        with vcr.use_cassette(
          'tests/data/vcr_cassettes/test_s3/replication_rule_no_bucket.yaml',
           record_mode='none'
        ):
            resources = p.run()
            self.assertEqual(len(resources), 1)
            self.assertTrue("Replication" in resources[0])
            self.assertEqual(len(resources[0].get("c7n:ListItemMatches")), 1)

    def test_s3_bucket_key_enabled(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.BucketEncryption, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        factory = self.replay_flight_data('test_s3_bucket_key_enabled')

        p = self.load_policy(
            {
                'name': 'test-s3-bucket-key-enabled',
                'resource': 'aws.s3',
                'filters': [
                    {
                        'type': 'bucket-encryption',
                        'bucket_key_enabled': True
                    },
                    {
                        'type': 'value',
                        'key': 'Name',
                        'value': 'c7n-test-s3-bucket',
                        'op': 'contains'
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_s3_bucket_key_disabled(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.BucketEncryption, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        factory = self.replay_flight_data('test_s3_bucket_key_disabled')

        p = self.load_policy(
            {
                'name': 'test-s3-bucket-key-disabled',
                'resource': 'aws.s3',
                'filters': [
                    {
                        'type': 'bucket-encryption',
                        'bucket_key_enabled': False
                    },
                    {
                        'type': 'value',
                        'key': 'Name',
                        'value': 'c7n-test-s3-bucket',
                        'op': 'contains'
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_bucket_encryption_invalid(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                'name': 'test-s3-bucket-encryption-invalid',
                'resource': 'aws.s3',
                'filters': [
                    {
                        'type': 'bucket-encryption',
                        'bucket_key_enabled': False,
                        'key': 'alias/foobar'
                    },
                    {
                        'type': 'value',
                        'key': 'Name',
                        'value': 'c7n-test-s3-bucket',
                        'op': 'contains'
                    }
                ]
            },
        )


class S3ObjectLockFilterTest(BaseTest):
    def test_query(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.S3LockConfigurationFilter, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        factory = self.replay_flight_data('test_s3_bucket_object_lock_configuration')

        p = self.load_policy(
            {
                'name': 'test-s3-bucket-key-disabled',
                'resource': 'aws.s3',
                'filters': [
                    {
                        'type': 'lock-configuration',
                        'key': 'Rule.DefaultRetention.Mode',
                        'value': 'GOVERNANCE',
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-s3-bucket')
        self.assertEqual(
            resources[0]['c7n:ObjectLockConfiguration']['Rule']['DefaultRetention']['Mode'],
            'GOVERNANCE'
        )

    def test_query_exception(self):
        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3.S3LockConfigurationFilter, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        log_mock = mock.MagicMock()
        self.patch(s3.S3LockConfigurationFilter, "log", log_mock)

        factory = self.replay_flight_data('test_s3_bucket_object_lock_configuration_exception')
        p = self.load_policy(
            {
                'name': 'test-s3-bucket-key-disabled',
                'resource': 'aws.s3',
                'filters': [
                    {
                        'type': 'lock-configuration',
                        'key': 'Rule.DefaultRetention.Mode',
                        'value': 'GOVERNANCE',
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        log_mock.error.assert_called()
