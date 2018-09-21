# Copyright 2017 Capital One Services, LLC
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

from .common import BaseTest


class Route53HostedZoneTest(BaseTest):

    def test_hostedzone_shield(self):
        session_factory = self.replay_flight_data("test_zone_shield_enable")
        p = self.load_policy(
            {
                "name": "zone-activate",
                "resource": "hostedzone",
                "filters": [
                    {"Config.PrivateZone": False},
                    {"Name": "invitro.cloud."},
                    {"type": "shield-enabled", "state": False},
                ],
                "actions": ["set-shield"],
            },
            session_factory=session_factory,
        )
        self.assertEqual(len(p.run()), 1)
        p = self.load_policy(
            {
                "name": "zone-verify",
                "resource": "hostedzone",
                "filters": [{"type": "shield-enabled", "state": True}],
            },
            session_factory=session_factory,
        )
        self.assertEqual(p.run()[0]["Id"], "/hostedzone/XXXXURLYV5DGGG")

    def test_route53_hostedzone_tag(self):
        session_factory = self.replay_flight_data("test_route53_hostedzone_tag")

        p = self.load_policy(
            {
                "name": "hostedzone-tag-records",
                "resource": "hostedzone",
                "filters": [
                    {
                        "type": "value",
                        "key": "ResourceRecordSetCount",
                        "value": 2,
                        "op": "gte",
                    }
                ],
                "actions": [{"type": "tag", "key": "abc", "value": "xyz"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        _id = resources[0]["Id"].split("/")[-1]
        tags = client.list_tags_for_resource(ResourceType="hostedzone", ResourceId=_id)
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 1)
        self.assertTrue("abc" in tags["ResourceTagSet"]["Tags"][0].values())

    def test_route53_hostedzone_untag(self):
        session_factory = self.replay_flight_data("test_route53_hostedzone_untag")

        p = self.load_policy(
            {
                "name": "hostedzone-untag-records",
                "resource": "hostedzone",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["abc"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        _id = resources[0]["Id"].split("/")[-1]
        tags = client.list_tags_for_resource(ResourceType="hostedzone", ResourceId=_id)
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 0)

    def test_route53_hostedzone_markop(self):
        session_factory = self.replay_flight_data("test_route53_hostedzone_markop")

        p = self.load_policy(
            {
                "name": "hostedzone-markop-records",
                "resource": "hostedzone",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "mark-for-op", "op": "notify", "days": 4}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        _id = resources[0]["Id"].split("/")[-1]
        tags = client.list_tags_for_resource(ResourceType="hostedzone", ResourceId=_id)
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 2)
        self.assertTrue("abc" in tags["ResourceTagSet"]["Tags"][0].values())


class Route53HealthCheckTest(BaseTest):

    def test_route53_healthcheck_tag(self):
        session_factory = self.replay_flight_data("test_route53_healthcheck_tag")

        p = self.load_policy(
            {
                "name": "healthcheck-tag-records",
                "resource": "healthcheck",
                "filters": [
                    {
                        "type": "value",
                        "key": "HealthCheckConfig.FailureThreshold",
                        "value": 3,
                        "op": "gte",
                    }
                ],
                "actions": [{"type": "tag", "key": "abc", "value": "xyz"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        tags = client.list_tags_for_resource(
            ResourceType="healthcheck", ResourceId=resources[0]["Id"]
        )
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 2)
        self.assertTrue("abc" in tags["ResourceTagSet"]["Tags"][0].values())

    def test_route53_healthcheck_untag(self):
        session_factory = self.replay_flight_data("test_route53_healthcheck_untag")

        p = self.load_policy(
            {
                "name": "healthcheck-untag-records",
                "resource": "healthcheck",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["abc"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        tags = client.list_tags_for_resource(
            ResourceType="healthcheck", ResourceId=resources[0]["Id"]
        )
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 1)  # Name is a tag
        self.assertTrue("Name" in tags["ResourceTagSet"]["Tags"][0].values())

    def test_route53_healthcheck_markop(self):
        session_factory = self.replay_flight_data("test_route53_healthcheck_markop")

        p = self.load_policy(
            {
                "name": "healthcheck-markop-records",
                "resource": "healthcheck",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "mark-for-op", "op": "notify", "days": 4}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        _id = resources[0]["Id"].split("/")[-1]
        tags = client.list_tags_for_resource(ResourceType="healthcheck", ResourceId=_id)
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 3)
        self.assertTrue("maid_status" in tags["ResourceTagSet"]["Tags"][1].values())


class Route53DomainTest(BaseTest):

    def test_route53_domain_auto_renew(self):
        session_factory = self.replay_flight_data("test_route53_domain")
        p = self.load_policy(
            {
                "name": "r53domain-auto-renew",
                "resource": "r53domain",
                "filters": [{"type": "value", "key": "AutoRenew", "value": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_route53_domain_transfer_lock(self):
        session_factory = self.replay_flight_data("test_route53_domain")
        p = self.load_policy(
            {
                "name": "r53domain-transfer-lock",
                "resource": "r53domain",
                "filters": [{"type": "value", "key": "TransferLock", "value": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_route53_domain_add_tag(self):
        session_factory = self.replay_flight_data("test_route53_domain_add_tag")
        p = self.load_policy(
            {
                "name": "r53domain-add-tag",
                "resource": "r53domain",
                "filters": [{"tag:TestTag": "absent"}],
                "actions": [{"type": "tag", "key": "TestTag", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("route53domains")
        tags = client.list_tags_for_domain(DomainName=resources[0]["DomainName"])[
            "TagList"
        ]
        self.assertEqual([tags[0]["Key"], tags[0]["Value"]], ["TestTag", "TestValue"])

    def test_route53_domain_remove_tag(self):
        session_factory = self.replay_flight_data("test_route53_domain_remove_tag")
        p = self.load_policy(
            {
                "name": "r53domain-add-tag",
                "resource": "r53domain",
                "filters": [{"tag:TestTag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["TestTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("route53domains")
        tags = client.list_tags_for_domain(DomainName=resources[0]["DomainName"])[
            "TagList"
        ]
        self.assertEqual(len(tags), 0)
