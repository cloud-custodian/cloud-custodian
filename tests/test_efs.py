# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError

from .common import BaseTest, functional

import uuid
import time

from operator import itemgetter


class ElasticFileSystem(BaseTest):

    @functional
    def test_resource_manager(self):
        factory = self.replay_flight_data("test_efs_query")
        client = factory().client("efs")
        token = str(uuid.uuid4())
        fs_id = client.create_file_system(CreationToken=token).get("FileSystemId")
        self.addCleanup(client.delete_file_system, FileSystemId=fs_id)
        tags = [{"Key": "Name", "Value": "Somewhere"}]
        client.create_tags(FileSystemId=fs_id, Tags=tags)
        if self.recording:
            time.sleep(5)

        p = self.load_policy(
            {
                "name": "efs-query",
                "resource": "efs",
                "filters": [{"FileSystemId": fs_id}, {"tag:Name": "Somewhere"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Tags"], tags)

    def test_mount_target_loading(self):
        factory = self.replay_flight_data("test_efs_subresource")
        p = self.load_policy(
            {"name": "test-mount-targets", "resource": "efs-mount-target"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_mount_target_security_group(self):
        factory = self.replay_flight_data("test_efs_mount_secgroup")
        p = self.load_policy(
            {
                "name": "test-mount-secgroup",
                "resource": "efs-mount-target",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "GroupId",
                        "value": "sg-ccf3a8a4",
                    },
                    # Use the same filter twice to excercise cache code
                    {
                        "type": "security-group",
                        "key": "GroupId",
                        "value": "sg-ccf3a8a4",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        resources = sorted(resources, key=itemgetter("MountTargetId"))
        self.assertEqual(resources[0]["MountTargetId"], "fsmt-a47385dd")

    def test_delete(self):
        factory = self.replay_flight_data("test_efs_delete")
        p = self.load_policy(
            {
                "name": "efs-query",
                "resource": "efs",
                "filters": [{"Name": "MyDocs"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "MyDocs")
        client = factory().client("efs")
        state = client.describe_file_systems().get("FileSystems", [])
        self.assertEqual(state, [])

    def test_kms_alias(self):
        factory = self.replay_flight_data("test_efs_kms_key_filter")
        p = self.load_policy(
            {
                "name": "efs-kms-alias",
                "resource": "efs",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "^(alias/aws/)",
                        "op": "regex"
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['KmsKeyId'],
            'arn:aws:kms:us-east-1:644160558196:key/8785aeb9-a616-4e2b-bbd3-df3cde76bcc5') # NOQA

    def test_enable_lifecycle_policy(self):
        factory = self.replay_flight_data("test_enable_lifecycle_policy")
        client = factory().client("efs")
        res = client.describe_lifecycle_configuration(FileSystemId="fs-fac23c7a")
        self.assertEqual(res.get('LifecyclePolicies'), [])
        p = self.load_policy(
            {
                "name": "efs-lifecycle-policy",
                "resource": "efs",
                "filters": [{"Name": "c7n-test"}],
                "actions": [
                    {
                        "type": "configure-lifecycle-policy",
                        "state": "enable",
                        "rules": [{'TransitionToIA': 'AFTER_7_DAYS'}],
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "c7n-test")
        self.assertEqual(resources[0]["FileSystemId"], "fs-fac23c7a")
        response = client.describe_lifecycle_configuration(FileSystemId="fs-fac23c7a")
        self.assertEqual(response.get('LifecyclePolicies'), [{'TransitionToIA': 'AFTER_7_DAYS'}])

    def test_disable_lifecycle_policy(self):
        factory = self.replay_flight_data("test_disable_lifecycle_policy")
        client = factory().client("efs")
        res = client.describe_lifecycle_configuration(FileSystemId="fs-fac23c7a")
        self.assertEqual(res.get('LifecyclePolicies'), [{'TransitionToIA': 'AFTER_7_DAYS'}])
        p = self.load_policy(
            {
                "name": "efs-lifecycle-policy-disable",
                "resource": "efs",
                "filters": [{"Name": "c7n-test"}],
                "actions": [
                    {
                        "type": "configure-lifecycle-policy",
                        "state": "disable",
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "c7n-test")
        self.assertEqual(resources[0]["FileSystemId"], "fs-fac23c7a")
        response = client.describe_lifecycle_configuration(FileSystemId="fs-fac23c7a")
        self.assertEqual(response.get('LifecyclePolicies'), [])

    def test_lifecycle_policy_validation_error(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "efs-lifecycle",
                "resource": "efs",
                "filters": [{"Name": "c7n-test"}],
                "actions": [{"type": "configure-lifecycle-policy", "state": "enable"}],
            }
        )

    def test_filter_lifecycle_policy_present(self):
        factory = self.replay_flight_data("test_filter_lifecycle_policy_present")
        p = self.load_policy(
            {
                "name": "efs-lifecycle-policy-enabled",
                "resource": "efs",
                "filters": [{"type": "lifecycle-policy",
                            "state": "present"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FileSystemId"], "fs-5f61b0df")

    def test_filter_lifecycle_policy_absent(self):
        factory = self.replay_flight_data("test_filter_lifecycle_policy_absent")
        p = self.load_policy(
            {
                "name": "efs-lifecycle-policy-disabled",
                "resource": "efs",
                "filters": [{"type": "lifecycle-policy",
                            "state": "absent"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FileSystemId"], "fs-a4cc1c24")

    def test_filter_lifecycle_policy_value(self):
        factory = self.replay_flight_data("test_filter_lifecycle_policy_value")
        p = self.load_policy(
            {
                "name": "efs-lifecycle-policy-enabled",
                "resource": "efs",
                "filters": [{"type": "lifecycle-policy",
                            "state": "present", "value": "AFTER_7_DAYS"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FileSystemId"], "fs-5f61b0df")
