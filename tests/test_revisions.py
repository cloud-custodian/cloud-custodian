# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest import mock

import jsonpatch

from c7n.filters.revisions import JsonDiff
from c7n.resources.vpc import SecurityGroupDiff, SecurityGroupPatch
from .common import BaseTest


class SGDiffLibTest(BaseTest):

    def test_sg_diff_remove_ingress(self):
        factory = self.replay_flight_data("test_sg_config_ingres_diff")
        p = self.load_policy(
            {
                "name": "sg-differ",
                "resource": "security-group",
                "filters": [
                    {"GroupId": "sg-65229a0c"},
                    {
                        "type": "diff",
                        "selector": "date",
                        "selector_value": "2017/01/27 00:40Z",
                    },
                ],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.maxDiff = None
        self.assertEqual(
            resources[0]["c7n:diff"],
            {
                "ingress": {
                    "removed": [
                        {
                            u"FromPort": 0,
                            u"IpProtocol": u"tcp",
                            u"IpRanges": [],
                            u"Ipv6Ranges": [],
                            u"PrefixListIds": [],
                            u"ToPort": 0,
                            u"UserIdGroupPairs": [
                                {u"GroupId": u"sg-aa6c90c3", u"UserId": u"644160558196"}
                            ],
                        }
                    ]
                }
            },
        )

    def test_json_diff_pitr(self):
        factory = self.replay_flight_data("test_sg_config_diff")
        p = self.load_policy(
            {
                "name": "sg-differ",
                "resource": "security-group",
                "filters": [
                    {"GroupId": "sg-a38ed1de"},
                    {
                        "type": "json-diff",
                        "selector": "date",
                        "selector_value": "2016/12/11 17:25Z",
                    },
                ],
            },
            session_factory=factory,
        )

        # jsonpatch versions differ in the patch they emit for the same
        # change, so check that the patch is correct, not its exact ops.
        with mock.patch.object(
                JsonDiff, "diff", autospec=True, side_effect=JsonDiff.diff) as diff:
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(diff.call_count, 1)
        jdiff, source, target = diff.call_args.args
        patch = resources[0]["c7n:diff"]
        self.assertTrue(patch)
        self.assertEqual(
            jsonpatch.apply_patch(jdiff.sanitize_revision(source), patch),
            jdiff.sanitize_revision(target))

    def test_sg_diff_pitr(self):
        factory = self.replay_flight_data("test_sg_config_diff")
        p = self.load_policy(
            {
                "name": "sg-differ",
                "resource": "security-group",
                "filters": [
                    {"GroupId": "sg-a38ed1de"},
                    {
                        "type": "diff",
                        "selector": "date",
                        "selector_value": "2016/12/11 17:25Z",
                    },
                ],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.maxDiff = None
        self.assertEqual(
            resources[0]["c7n:diff"],
            {
                "egress": {
                    "added": [
                        {
                            u"IpProtocol": u"-1",
                            u"IpRanges": [{u"CidrIp": u"0.0.0.0/0"}],
                            u"Ipv6Ranges": [],
                            u"PrefixListIds": [],
                            u"UserIdGroupPairs": [
                                {u"GroupId": u"sg-a08ed1dd", u"UserId": u"644160558196"}
                            ],
                        }
                    ],
                    "removed": [
                        {
                            u"IpProtocol": u"-1",
                            u"IpRanges": [{u"CidrIp": u"0.0.0.0/0"}],
                            u"Ipv6Ranges": [],
                            u"PrefixListIds": [],
                            u"UserIdGroupPairs": [],
                        }
                    ],
                },
                "ingress": {
                    "added": [
                        {
                            u"FromPort": 22,
                            u"IpProtocol": u"tcp",
                            u"IpRanges": [{u"CidrIp": u"10.0.0.0/24"}],
                            u"Ipv6Ranges": [],
                            u"PrefixListIds": [],
                            u"ToPort": 22,
                            u"UserIdGroupPairs": [],
                        },
                        {
                            u"FromPort": 8485,
                            u"IpProtocol": u"tcp",
                            u"IpRanges": [],
                            u"Ipv6Ranges": [],
                            u"PrefixListIds": [],
                            u"ToPort": 8485,
                            u"UserIdGroupPairs": [
                                {u"GroupId": u"sg-a38ed1de", u"UserId": u"644160558196"}
                            ],
                        },
                    ]
                },
                "tags": {"added": {u"Scope": u"account"}},
            },
        )

    def test_sg_patch_pitr(self):
        factory = self.replay_flight_data("test_sg_config_patch_pitr")
        p = self.load_policy(
            {
                "name": "sg-differ",
                "resource": "security-group",
                "filters": [
                    {"GroupId": "sg-a38ed1de"},
                    {
                        "type": "diff",
                        "selector": "date",
                        "selector_value": "2016/12/11 17:25Z",
                    },
                ],
                "actions": ["patch"],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        current_resource = factory().client("ec2").describe_security_groups(
            GroupIds=["sg-a38ed1de"]
        )[
            "SecurityGroups"
        ][
            0
        ]

        self.maxDiff = None
        self.assertEqual(
            current_resource, resources[0]["c7n:previous-revision"]["resource"]
        )

    def test_sg_diff_patch(self):
        factory = self.replay_flight_data("test_security_group_revisions_delta")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.42.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="allow-access", VpcId=vpc_id, Description="inbound access"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg_id)

        client.create_tags(
            Resources=[sg_id],
            Tags=[
                {"Key": "NetworkLocation", "Value": "DMZ"},
                {"Key": "App", "Value": "blue-moon"},
            ],
        )
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "10.42.1.0/24"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 8080,
                    "ToPort": 8080,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
            ],
        )

        s1 = client.describe_security_groups(GroupIds=[sg_id])["SecurityGroups"][0]

        # Modify state
        client.create_tags(
            Resources=[sg_id],
            Tags=[
                {"Key": "App", "Value": "red-moon"},
                {"Key": "Stage", "Value": "production"},
            ],
        )
        client.revoke_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 8080,
                    "ToPort": 8080,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )
        s2 = client.describe_security_groups(GroupIds=[sg_id])["SecurityGroups"][0]

        # Apply reverse delta
        self.maxDiff = None
        self.assertEqual(
            {
                "ingress": {
                    "added": [
                        {
                            u"FromPort": 80,
                            u"IpProtocol": "tcp",
                            u"IpRanges": [{u"CidrIp": "0.0.0.0/0"}],
                            u"Ipv6Ranges": [],
                            u"PrefixListIds": [],
                            u"ToPort": 80,
                            u"UserIdGroupPairs": [],
                        }
                    ],
                    "removed": [
                        {
                            u"FromPort": 8080,
                            u"IpProtocol": "tcp",
                            u"IpRanges": [{u"CidrIp": "0.0.0.0/0"}],
                            u"Ipv6Ranges": [],
                            u"PrefixListIds": [],
                            u"ToPort": 8080,
                            u"UserIdGroupPairs": [],
                        }
                    ],
                },
                "tags": {
                    "added": {"Stage": "production"}, "updated": {"App": "red-moon"}
                },
            },
            SecurityGroupDiff().diff(s1, s2),
        )

        SecurityGroupPatch().apply_delta(client, s2, SecurityGroupDiff().diff(s2, s1))

        # Compare to origin
        s3 = client.describe_security_groups(GroupIds=[sg_id])["SecurityGroups"][0]

        self.assertEqual(s1, s3)
