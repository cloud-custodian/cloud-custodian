# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime
from dateutil import zoneinfo

from .common import BaseTest
from botocore.exceptions import ClientError
from c7n.resources.asg import NotEncryptedFilter


class LaunchConfigTest(BaseTest):

    def test_config_unused(self):
        factory = self.replay_flight_data("test_launch_config_unused")
        p = self.load_policy(
            {
                "name": "unused-cfg",
                "resource": "launch-config",
                "filters": [{"type": "unused"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["LaunchConfigurationName"], "CloudClusterCopy")

    def test_config_delete(self):
        factory = self.replay_flight_data("test_launch_config_delete")
        p = self.load_policy(
            {
                "name": "delete-cfg",
                "resource": "launch-config",
                "filters": [{"LaunchConfigurationName": "CloudClusterCopy"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["LaunchConfigurationName"], "CloudClusterCopy")


class TestUserData(BaseTest):

    def test_regex_filter(self):
        session_factory = self.replay_flight_data("test_launch_config_userdata")
        policy = self.load_policy(
            {
                "name": "launch_config_userdata",
                "resource": "asg",
                'filters': [
                    {
                        'or': [
                            {'type': 'user-data', 'op': 'regex', 'value': '(?smi).*A[KS]IA'}
                        ]
                    }
                ],
            },
            session_factory=session_factory
        )
        resources = policy.run()
        self.assertGreater(len(resources), 0)


class AutoScalingTest(BaseTest):

    def get_ec2_tags(self, ec2, instance_id):
        results = ec2.describe_tags(
            Filters=[
                {"Name": "resource-id", "Values": [instance_id]},
                {"Name": "resource-type", "Values": ["instance"]},
            ]
        )[
            "Tags"
        ]
        return {t["Key"]: t["Value"] for t in results}

    def test_asg_delete(self):
        factory = self.replay_flight_data("test_asg_delete")
        p = self.load_policy(
            {
                "name": "asg-delete",
                "resource": "asg",
                "filters": [{"AutoScalingGroupName": "ContainersFTW"}],
                "actions": [{"type": "delete", "force": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["AutoScalingGroupName"], "ContainersFTW")

    def test_asg_non_encrypted_filter(self):
        factory = self.replay_flight_data("test_asg_non_encrypted_filter")
        p = self.load_policy(
            {
                "name": "asg-encrypted-filter",
                "resource": "asg",
                "filters": [{"type": "not-encrypted"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Unencrypted"], ["Image", "LaunchConfig"])

    def test_get_bad_snapshot_malformed(self):
        operation_name = "DescribeSnapshots"
        error_response = {
            "Error": {
                "Message": 'Invalid id: "snap-malformedsnap"',
                "Code": "InvalidSnapshotID.Malformed",
            }
        }
        e = ClientError(error_response, operation_name)
        snap = NotEncryptedFilter.get_bad_snapshot(e)
        self.assertEquals(snap, "snap-malformedsnap")

    def test_get_bad_snapshot_notfound(self):
        operation_name = "DescribeSnapshots"
        error_response = {
            "Error": {
                "Message": "The snapshot 'snap-notfound' does not exist.",
                "Code": "InvalidSnapshot.NotFound",
            }
        }
        e = ClientError(error_response, operation_name)
        snap = NotEncryptedFilter.get_bad_snapshot(e)
        self.assertEquals(snap, "snap-notfound")

    def test_asg_image_age_filter(self):
        factory = self.replay_flight_data("test_asg_image_age_filter")
        p = self.load_policy(
            {
                "name": "asg-cfg-filter",
                "resource": "asg",
                "filters": [{"type": "image-age", "days": 90}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_asg_config_filter(self):
        factory = self.replay_flight_data("test_asg_config_filter")
        p = self.load_policy(
            {
                "name": "asg-cfg-filter",
                "resource": "asg",
                "filters": [
                    {"type": "launch-config", "key": "ImageId", "value": "ami-9abea4fb"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_asg_vpc_filter(self):
        factory = self.replay_flight_data("test_asg_vpc_filter")
        p = self.load_policy(
            {
                "name": "asg-vpc-filter",
                "resource": "asg",
                "filters": [{"type": "vpc-id", "value": "vpc-d2d616b5"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["LaunchConfigurationName"], "foo-bar")

    def test_asg_tag_and_propagate(self):
        factory = self.replay_flight_data("test_asg_tag")
        p = self.load_policy(
            {
                "name": "asg-tag",
                "resource": "asg",
                "filters": [{"tag:Platform": "ubuntu"}],
                "actions": [
                    {
                        "type": "tag",
                        "key": "CustomerId",
                        "value": "GetSome",
                        "propagate": True,
                    },
                    {
                        "type": "propagate-tags",
                        "trim": True,
                        "tags": ["CustomerId", "Platform"],
                    },
                ],
            },
            session_factory=factory,
        )

        session = factory()
        client = session.client("autoscaling")

        # Put an orphan tag on an instance
        result = client.describe_auto_scaling_groups()["AutoScalingGroups"].pop()
        ec2 = session.client("ec2")
        instance_id = result["Instances"][0]["InstanceId"]
        ec2.create_tags(
            Resources=[instance_id], Tags=[{"Key": "Home", "Value": "Earth"}]
        )

        # Run the policy
        resources = p.run()
        self.assertEqual(len(resources), 1)

        result = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
        )[
            "AutoScalingGroups"
        ].pop()
        tag_map = {
            t["Key"]: (t["Value"], t["PropagateAtLaunch"]) for t in result["Tags"]
        }
        self.assertTrue("CustomerId" in tag_map)
        self.assertEqual(tag_map["CustomerId"][0], "GetSome")
        self.assertEqual(tag_map["CustomerId"][1], True)

        tag_map = self.get_ec2_tags(ec2, instance_id)
        self.assertTrue("CustomerId" in tag_map)
        self.assertFalse("Home" in tag_map)

    def test_asg_remove_tag(self):
        factory = self.replay_flight_data("test_asg_remove_tag")
        p = self.load_policy(
            {
                "name": "asg-remove-tag",
                "resource": "asg",
                "filters": [{"tag:CustomerId": "not-null"}],
                "actions": [{"type": "remove-tag", "key": "CustomerId"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("autoscaling")
        result = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
        )[
            "AutoScalingGroups"
        ].pop()
        tag_map = {
            t["Key"]: (t["Value"], t["PropagateAtLaunch"]) for t in result["Tags"]
        }
        self.assertFalse("CustomerId" in tag_map)

    def test_asg_mark_for_op(self):
        factory = self.replay_flight_data("test_asg_mark_for_op")
        p = self.load_policy(
            {
                "name": "asg-mark-for-op",
                "resource": "asg",
                "filters": [{"tag:Platform": "ubuntu"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "key": "custodian_action",
                        "op": "suspend",
                        "days": 1,
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("autoscaling")
        result = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
        )[
            "AutoScalingGroups"
        ].pop()
        tag_map = {t["Key"]: t["Value"] for t in result["Tags"]}
        self.assertTrue("custodian_action" in tag_map)
        self.assertTrue("suspend@" in tag_map["custodian_action"])

    def test_asg_mark_for_op_hours(self):
        session_factory = self.replay_flight_data("test_asg_mark_for_op_hours")
        session = session_factory(region="us-east-1")
        asg = session.client("autoscaling")
        localtz = zoneinfo.gettz("America/New_York")
        dt = datetime.now(localtz)
        dt = dt.replace(
            year=2018, month=2, day=20, hour=12, minute=42, second=0, microsecond=0
        )

        policy = self.load_policy(
            {
                "name": "asg-mark-for-op-hours",
                "resource": "asg",
                "filters": [{"tag:Service": "absent"}],
                "actions": [{"type": "mark-for-op", "op": "delete", "hours": 1}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        describe_auto_scaling_groups = asg.describe_auto_scaling_groups(
            AutoScalingGroupNames=["marked"]
        )
        resource = describe_auto_scaling_groups["AutoScalingGroups"][0]
        tags = [t["Value"] for t in resource["Tags"] if t["Key"] == "maid_status"]
        result = datetime.strptime(
            tags[0].strip().split("@", 1)[-1], "%Y/%m/%d %H%M %Z"
        ).replace(
            tzinfo=localtz
        )
        self.assertEqual(result, dt)

    def test_asg_marked_for_op_hours(self):
        session_factory = self.replay_flight_data("test_asg_marked_for_op_hours")
        policy = self.load_policy(
            {
                "name": "asg-marked-for-delete",
                "resource": "asg",
                "filters": [{"type": "marked-for-op", "op": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["AutoScalingGroupName"], "marked")

    def test_asg_rename_tag(self):
        factory = self.replay_flight_data("test_asg_rename")
        p = self.load_policy(
            {
                "name": "asg-rename-tag",
                "resource": "asg",
                "filters": [{"tag:Platform": "ubuntu"}],
                "actions": [
                    {"type": "rename-tag", "source": "Platform", "dest": "Linux"}
                ],
            },
            session_factory=factory,
        )

        # Fetch ASG
        session = factory()
        client = session.client("autoscaling")
        result = client.describe_auto_scaling_groups()["AutoScalingGroups"].pop()

        # Fetch instance and make sure it has tags
        ec2 = session.client("ec2")
        instance_id = result["Instances"][0]["InstanceId"]

        tag_map = self.get_ec2_tags(ec2, instance_id)
        self.assertTrue("Platform" in tag_map)
        self.assertFalse("Linux" in tag_map)

        # Run the policy
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Validate the ASG tag changed
        result = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
        )[
            "AutoScalingGroups"
        ].pop()
        tag_map = {
            t["Key"]: (t["Value"], t["PropagateAtLaunch"]) for t in result["Tags"]
        }
        self.assertFalse("Platform" in tag_map)
        self.assertTrue("Linux" in tag_map)

        tag_map = self.get_ec2_tags(ec2, instance_id)
        self.assertFalse("Platform" in tag_map)
        self.assertTrue("Linux" in tag_map)

    def test_asg_suspend(self):
        factory = self.replay_flight_data("test_asg_suspend")
        p = self.load_policy(
            {
                "name": "asg-suspend",
                "resource": "asg",
                "filters": [{"tag:Platform": "not-null"}],
                "actions": ["suspend"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("autoscaling")
        result = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
        )[
            "AutoScalingGroups"
        ].pop()
        self.assertTrue(result["SuspendedProcesses"])

    def test_asg_suspend_when_no_instances(self):
        factory = self.replay_flight_data("test_asg_suspend_when_no_instances")
        client = factory().client("autoscaling")

        # Ensure we have a non-suspended ASG with no instances
        name = "zero-instances"
        result = client.describe_auto_scaling_groups(AutoScalingGroupNames=[name])[
            "AutoScalingGroups"
        ].pop()
        self.assertEqual(len(result["SuspendedProcesses"]), 0)
        self.assertEqual(len(result["Instances"]), 0)

        # Run policy and verify suspend occurs
        p = self.load_policy(
            {
                "name": "asg-suspend",
                "resource": "asg",
                "filters": [{"AutoScalingGroupName": name}],
                "actions": ["suspend"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        result = client.describe_auto_scaling_groups(AutoScalingGroupNames=[name])[
            "AutoScalingGroups"
        ].pop()
        self.assertTrue(result["SuspendedProcesses"])

    def test_asg_resume(self):
        factory = self.replay_flight_data("test_asg_resume")
        p = self.load_policy(
            {
                "name": "asg-suspend",
                "resource": "asg",
                "filters": [{"tag:Platform": "not-null"}],
                "actions": [{"type": "resume", "delay": 0.1}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("autoscaling")
        result = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
        )[
            "AutoScalingGroups"
        ].pop()
        self.assertFalse(result["SuspendedProcesses"])

    def test_asg_resize_save_to_tag(self):
        factory = self.replay_flight_data("test_asg_resize_save_to_tag")
        p = self.load_policy(
            {
                "name": "asg-resize",
                "resource": "asg",
                "filters": [{"tag:CustodianUnitTest": "not-null"}],
                "actions": [
                    {
                        "type": "resize",
                        "min-size": 0,
                        "desired-size": 0,
                        "save-options-tag": "OffHoursPrevious",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("autoscaling")
        result = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
        )[
            "AutoScalingGroups"
        ].pop()
        # test that we set ASG size to zero
        self.assertEqual(result["MinSize"], 0)
        self.assertEqual(result["DesiredCapacity"], 0)
        tag_map = {t["Key"]: t["Value"] for t in result["Tags"]}
        # test that we saved state to a tag
        self.assertTrue("OffHoursPrevious" in tag_map)
        self.assertEqual(
            tag_map["OffHoursPrevious"], "DesiredCapacity=2;MinSize=2;MaxSize=2"
        )

    def test_asg_resize_restore_from_tag(self):
        factory = self.replay_flight_data("test_asg_resize_restore_from_tag")
        p = self.load_policy(
            {
                "name": "asg-resize",
                "resource": "asg",
                "filters": [
                    {"tag:CustodianUnitTest": "not-null"},
                    {"tag:OffHoursPrevious": "not-null"},
                ],
                "actions": [
                    {"type": "resize", "restore-options-tag": "OffHoursPrevious"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("autoscaling")
        result = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
        )[
            "AutoScalingGroups"
        ].pop()
        # test that we set ASG min and desired back from 0 to 2
        self.assertEqual(result["MinSize"], 2)
        self.assertEqual(result["DesiredCapacity"], 2)

    def test_asg_resize_to_current(self):
        factory = self.replay_flight_data("test_asg_resize_to_current")
        # test scenario:
        # - create ASG with min=2, desired=2 running in account A
        # - launch config specifies a test AMI in account B
        # - remove permissions on the AMI for account A
        # - kill one of the 2 running instances, wait until the ASG sees that
        # - leaves min=2, desired=2, running=1 and it's unable to launch more
        p = self.load_policy(
            {
                "name": "asg-resize",
                "resource": "asg",
                "filters": [
                    {"type": "capacity-delta"}, {"tag:CustodianUnitTest": "not-null"}
                ],
                "actions": [{"type": "resize", "desired-size": "current"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("autoscaling")
        result = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
        )[
            "AutoScalingGroups"
        ].pop()
        # test that we changed ASG min and desired from 2 to 1
        self.assertEqual(result["MinSize"], 1)
        self.assertEqual(result["DesiredCapacity"], 1)

    def test_asg_third_ami_filter(self):
        factory = self.replay_flight_data("test_asg_invalid_third_ami")
        p = self.load_policy(
            {
                "name": "asg-invalid-filter-3ami",
                "resource": "asg",
                "filters": ["invalid"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_asg_invalid_filter_good(self):
        factory = self.replay_flight_data("test_asg_invalid_filter_good")
        p = self.load_policy(
            {"name": "asg-invalid-filter", "resource": "asg", "filters": ["invalid"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_asg_invalid_filter_bad(self):
        factory = self.replay_flight_data("test_asg_invalid_filter_bad")
        p = self.load_policy(
            {"name": "asg-invalid-filter", "resource": "asg", "filters": ["invalid"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        s = set([x[0] for x in resources[0]["Invalid"]])
        self.assertTrue("invalid-subnet" in s)
        self.assertTrue("invalid-security-group" in s)

    def test_asg_subnet(self):
        factory = self.replay_flight_data("test_asg_subnet")
        p = self.load_policy(
            {
                "name": "asg-sub",
                "resource": "asg",
                "filters": [
                    {
                        "type": "subnet",
                        "match-resource": True,
                        "key": "tag:NetworkLocation",
                        "value": "",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted(resources[0]["c7n:matched-subnets"]),
            sorted(["subnet-65dbce1d", "subnet-b77a4ffd", "subnet-db9f62b2"]),
        )

    def test_asg_security_group_not_matched(self):
        factory = self.replay_flight_data("test_asg_security_group_not_matched")
        p = self.load_policy(
            {
                "name": "asg-sg",
                "resource": "asg",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "tag:NetworkLocation",
                        "op": "not-equal",
                        "value": "",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:matched-security-groups"], ["sg-0b3d3377"])

    def test_asg_security_group(self):
        factory = self.replay_flight_data("test_asg_security_group")
        p = self.load_policy(
            {
                "name": "asg-sg",
                "resource": "asg",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["AutoScalingGroupName"], "ContainersFTW")

    def test_asg_propagate_tag_filter(self):
        session = self.replay_flight_data("test_asg_propagate_tag_filter")
        policy = self.load_policy(
            {
                "name": "asg-propagated-tag-filter",
                "resource": "asg",
                "filters": [
                    {"type": "progagated-tags", "keys": ["Tag01", "Tag02", "Tag03"]}
                ],
            },
            session_factory=session,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["AutoScalingGroupName"], "c7n.asg.ec2.01")

        policy = self.load_policy(
            {
                "name": "asg-propagated-tag-filter",
                "resource": "asg",
                "filters": [
                    {"type": "propagated-tags", "keys": ["Tag01", "Tag02", "Tag03"]}
                ],
            },
            session_factory=session,
        )

        policy.validate()

    def test_asg_propagate_tag_missing(self):
        session = self.replay_flight_data("test_asg_propagate_tag_missing")
        policy = self.load_policy(
            {
                "name": "asg-propagated-tag-filter",
                "resource": "asg",
                "filters": [
                    {
                        "type": "progagated-tags",
                        "match": False,
                        "keys": ["Tag01", "Tag02", "Tag03"],
                    }
                ],
            },
            session_factory=session,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted([r["AutoScalingGroupName"] for r in resources]),
            ["c7n.asg.ec2.02", "c7n.asg.ec2.03"],
        )

    def test_asg_not_propagate_tag_match(self):
        session = self.replay_flight_data("test_asg_not_propagate_match")
        policy = self.load_policy(
            {
                "name": "asg-propagated-tag-filter",
                "resource": "asg",
                "filters": [
                    {
                        "type": "progagated-tags",
                        "keys": ["Tag01", "Tag02", "Tag03"],
                        "propagate": False,
                    }
                ],
            },
            session_factory=session,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["AutoScalingGroupName"], "c7n-asg-np-match")

    def test_asg_not_propagate_tag_missing(self):
        session = self.replay_flight_data("test_asg_not_propagate_missing")
        policy = self.load_policy(
            {
                "name": "asg-propagated-tag-filter",
                "resource": "asg",
                "filters": [
                    {
                        "type": "progagated-tags",
                        "keys": ["Tag01", "Tag02", "Tag03"],
                        "match": False,
                        "propagate": False,
                    }
                ],
            },
            session_factory=session,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["AutoScalingGroupName"], "c7n-asg-np-missing")

    def test_asg_filter_capacity_delta_match(self):
        factory = self.replay_flight_data("test_asg_filter_capacity_delta_match")
        p = self.load_policy(
            {
                "name": "asg-capacity-delta",
                "resource": "asg",
                "filters": [
                    {"type": "capacity-delta"}, {"tag:CustodianUnitTest": "not-null"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_asg_filter_capacity_delta_nomatch(self):
        factory = self.replay_flight_data("test_asg_filter_capacity_delta_nomatch")
        p = self.load_policy(
            {
                "name": "asg-capacity-delta",
                "resource": "asg",
                "filters": [
                    {"type": "capacity-delta"}, {"tag:CustodianUnitTest": "not-null"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)
