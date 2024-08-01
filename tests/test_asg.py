# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from dateutil import tz as tzutil

import pytest
from pytest_terraform import terraform

from .common import BaseTest

from c7n.exceptions import PolicyValidationError
from c7n.resources.asg import LaunchInfo
from c7n.resources.aws import shape_validate
from c7n.utils import jmespath_search


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


class AutoScalingTemplateTest(BaseTest):

    def test_asg_mixed_instance_templates(self):
        d = {
            "AutoScalingGroupName": "devx",
            "MixedInstancesPolicy": {
                "LaunchTemplate": {
                    "LaunchTemplateSpecification": {
                        "LaunchTemplateId": "lt-0877401c93c294001",
                        "LaunchTemplateName": "test",
                        "Version": "4"},
                    "Overrides": [{"InstanceType": "t1.micro"},
                                  {"InstanceType": "t2.small"}]
                },
                "InstancesDistribution": {
                    "OnDemandAllocationStrategy": "prioritized",
                    "OnDemandBaseCapacity": 1,
                    "OnDemandPercentageAboveBaseCapacity": 0,
                    "SpotAllocationStrategy": "capacity-optimized"
                }
            },
            "MinSize": 1,
            "MaxSize": 1,
            "DesiredCapacity": 1,
            "DefaultCooldown": 300,
            "AvailabilityZones": ["us-east-1d", "us-east-1e"],
            "HealthCheckType": "EC2",
            "HealthCheckGracePeriod": 300,
            "VPCZoneIdentifier": "subnet-3a334610,subnet-e3b194de"}

        p = self.load_policy({"name": "mixed-instance", "resource": "asg"})
        self.assertEqual(
            list(p.resource_manager.get_resource_manager(
                'launch-template-version').get_asg_templates([d]).keys()),
            [("lt-0877401c93c294001", "4")])
        self.assertEqual(
            LaunchInfo(p.resource_manager).get_launch_id(d), ("lt-0877401c93c294001", "4"))


@pytest.mark.audited
@terraform('aws_asg')
def test_asg_propagate_tag_action(test, aws_asg):

    factory = test.replay_flight_data('test_asg_propagate_tag_action')
    p = test.load_policy({
        'name': 'asg-tagger',
        'resource': 'aws.asg',
        'filters': [
            {'AutoScalingGroupName': aws_asg['aws_autoscaling_group.bar.id']},
            {'tag:Owner': 'absent'}
        ],
        'actions': [
            {'type': 'tag', 'key': 'Owner', 'value': 'Kapil', 'propagate': True},
            {'type': 'propagate-tags', 'tags': ['Owner']}]},
        session_factory=factory)
    resources = p.run()
    test.assertEqual(len(resources), 1)
    client = factory().client('ec2')
    itags = {t['Key']: t['Value'] for t in jmespath_search(
        'Reservations[0].Instances[0].Tags',
        client.describe_instances(
            InstanceIds=[resources[0]['Instances'][0]['InstanceId']]))}
    assert 'Owner' in itags
    assert itags['Owner'] == 'Kapil'


@pytest.mark.audited
@terraform("aws_asg_update")
def test_aws_asg_update(test, aws_asg_update):
    factory = test.replay_flight_data("test_aws_asg_update")
    p = test.load_policy(
        {
            "name": "asg-update",
            "resource": "aws.asg",
            "filters": [{
                "AutoScalingGroupName": aws_asg_update["aws_autoscaling_group.bar.id"]
            }],
            "actions": [{
                "type": "update",
                "default-cooldown": 600,
                "max-instance-lifetime": 604800,
                "new-instances-protected-from-scale-in": True,
                "capacity-rebalance": True,
            }],
        },
        session_factory=factory,
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)

    client = factory().client("autoscaling")
    result = client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[resources[0]["AutoScalingGroupName"]]
    )[
        "AutoScalingGroups"
    ].pop()
    test.assertEqual(result["DefaultCooldown"], 600)
    test.assertEqual(result["MaxInstanceLifetime"], 604800)
    test.assertTrue(result["NewInstancesProtectedFromScaleIn"])
    test.assertTrue(result["CapacityRebalance"])


def test_aws_asg_update_no_settings(test):
    factory = test.replay_flight_data("test_aws_asg_update")
    with test.assertRaises(PolicyValidationError):
        test.load_policy(
            {
                "name": "asg-update",
                "resource": "aws.asg",
                "actions": [{
                    "type": "update",
                }],
            },
            session_factory=factory,
        )


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

    def test_asg_non_encrypted_filter_with_templates(self):
        factory = self.replay_flight_data("test_asg_non_encrypted_filter_with_templates")
        p = self.load_policy(
            {
                "name": "asg-encrypted-with-launch-templates",
                "resource": "asg",
                "filters": [
                    {"type": "not-encrypted"},
                    {'LaunchTemplate': 'present'}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

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

    def test_asg_image_age_filter_template(self):
        factory = self.replay_flight_data("test_asg_image_age_filter_template")
        p = self.load_policy(
            {
                "name": "asg-cfg-filter",
                "resource": "asg",
                "filters": [
                    {"type": "image-age", "days": 1, 'op': 'ge'},
                    {"LaunchTemplate": "present"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_asg_image_age_filter_deleted_config(self):
        factory = self.replay_flight_data("test_asg_image_age_filter_deleted_config")
        p = self.load_policy(
            {
                "name": "asg-image-age-filter",
                "resource": "asg",
                "filters": [
                    {"tag:Env": "present"},
                    {"type": "image-age", "days": 5000, "op": "gt"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('Env' in resources[0].get('Tags')[1].values())

    def test_asg_image_filter_from_launch_template(self):
        factory = self.replay_flight_data("test_asg_image_filter_from_launch_template")
        p = self.load_policy(
            {
                "name": "asg-image-filter_lt",
                "resource": "asg",
                "filters": [
                    {
                        "type": "image",
                        "key": "Description",
                        "value": ".*CentOS7.*",
                        "op": "regex"
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_asg_image_filter_from_launch_config(self):
        factory = self.replay_flight_data("test_asg_image_filter_from_launch_config")
        p = self.load_policy(
            {
                "name": "asg-image-filter_lc",
                "resource": "asg",
                "filters": [
                    {
                        "type": "image",
                        "key": "Description",
                        "value": ".*Ubuntu1804.*",
                        "op": "regex"
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_asg_image_filter_from_lc_and_lt(self):
        factory = self.replay_flight_data("test_asg_image_filter_from_lc_and_lt")
        p = self.load_policy(
            {
                "name": "asg-image-filter_lc_lt",
                "resource": "asg",
                "filters": [
                    {
                        "type": "image",
                        "key": "Description",
                        "value": ".*AmazonLinux2.*",
                        "op": "regex"
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

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

    def test_asg_scaling_policy_filter(self):
        factory = self.replay_flight_data("test_asg_scaling_policy_filter")
        p = self.load_policy(
            {
                "name": "asg-sp-filter",
                "resource": "asg",
                "filters": [
                    {
                        "type": "scaling-policy",
                        "key": "PolicyType",
                        "value": "TargetTrackingScaling"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['AutoScalingGroupName'], 'asg-test-scaling-policy')
        self.assertTrue('c7n:matched-policies' in resources[0])
        self.assertTrue(
            resources[0]['c7n:matched-policies'][0]['PolicyName'], 'Target Tracking Policy')

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

    def test_asg_post_finding_format(self):
        factory = self.replay_flight_data('test_asg_mark_for_op')
        p = self.load_policy({
            'name': 'asg-post',
            'resource': 'aws.asg',
            'actions': [
                {'type': 'post-finding',
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
                'AwsAutoScalingAutoScalingGroup': {
                    'CreatedTime': '2016-05-16T18:31:32.276000+00:00',
                    'HealthCheckGracePeriod': 300,
                    'HealthCheckType': 'EC2',
                    'LaunchConfigurationName': 'CustodianASGTestCopyCopy',
                    'LoadBalancerNames': []}},
             'Id': 'arn:aws:autoscaling:us-west-2:619193117841:autoScalingGroup:650754f5-21d3-409f-b43a-fffdeb22910d:autoScalingGroupName/CustodianASG',  # noqa
             'Partition': 'aws',
             'Region': 'us-east-1',
             'Tags': {'Platform': 'ubuntu',
                      'custodian_action': (
                          'AutoScaleGroup does not meet org tag policy: '
                          'suspend@2016/05/21')},
             'Type': 'AwsAutoScalingAutoScalingGroup'})

        shape_validate(
            rfinding['Details']['AwsAutoScalingAutoScalingGroup'],
            'AwsAutoScalingAutoScalingGroupDetails', 'securityhub')

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
        localtz = tzutil.gettz("America/New_York")
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

    def test_valid_asg_with_launch_templates(self):
        factory = self.replay_flight_data("test_valid_asg_with_launch_templates")
        p = self.load_policy(
            {
                "name": "asg-valid-templates",
                "resource": "asg",
                "filters": [
                    {"type": "valid"},
                    {"LaunchTemplate": "present"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_asg_invalid_filter_validation(self):
        """Validate policy execution mode

        The valid/invalid filters should cause Lambda mode policies to fail, but
        pass for other execution modes whether specified explicitly or not.
        """
        base_policy = {
            "name": "asg-invalid-filter",
            "resource": "asg",
            "filters": ["invalid"],
        }

        # Policy should validate cleanly for pull mode, whether it's the implicit
        # default mode or specified explicitly.
        p = self.load_policy(base_policy)
        p.validate()
        p = self.load_policy({**base_policy, "mode": {"type": "pull"}})
        p.validate()

        with self.assertRaisesRegex(
            PolicyValidationError, "too many queries to be run in lambda"
        ):
            p = self.load_policy(
                {**base_policy, "mode": {"type": "periodic", "schedule": "rate(1 day)"}}
            )
            p.validate()

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

        s = {x[0] for x in resources[0]["Invalid"]}
        self.assertTrue("invalid-subnet" in s)
        self.assertTrue("invalid-security-group" in s)

    def test_asg_valid_without_subnets(self):
        factory = self.replay_flight_data("test_asg_valid_without_subnets")
        p = self.load_policy(
            {
                "name": "asg-valid-without-subnets",
                "resource": "asg",
                "filters": [
                    {"type": "valid"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

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

    def test_asg_propagate_tag_no_instances(self):
        factory = self.replay_flight_data("test_asg_propagate_tag_no_instances")
        p = self.load_policy(
            {
                "name": "asg-tag",
                "resource": "asg",
                "filters": [{"tag:Platform": "ubuntu"}],
                "actions": [
                    {
                        "type": "propagate-tags",
                        "trim": True,
                        "tags": ["CustomerId", "Platform"],
                    },
                ],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["AutoScalingGroupName"], "c7n.asg.ec2.01")

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


class AutoScalingPolicy(BaseTest):

    def test_asg_scaling_policy_enabled(self):
        factory = self.replay_flight_data("test_asg_scaling_policy_enabled")
        p = self.load_policy(
            {
                "name": "asg-sp-enabled",
                "resource": "scaling-policy",
                "filters": [
                    {"type": "value", "key": "PolicyName", "value": "Target Tracking Policy"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0].get('Enabled'))
