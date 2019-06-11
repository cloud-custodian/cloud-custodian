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

import jmespath
from .common import BaseTest, TestConfig as Config
from c7n.utils import local_session


class CloudFrontWaf(BaseTest):

    def test_waf(self):
        factory = self.replay_flight_data("test_distribution_waf")
        p = self.load_policy(
            {
                "name": "waf-cfront",
                "resource": "distribution",
                "filters": [{"type": "waf-enabled", "web-acl": "test", "state": False}],
                "actions": [{"type": "set-waf", "web-acl": "test", "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        p = self.load_policy(
            {
                "name": "waf-cfront",
                "resource": "distribution",
                "filters": [{"type": "waf-enabled", "web-acl": "test", "state": False}],
            },
            session_factory=factory,
        )
        self.assertEqual(p.run(), [])


class CloudFront(BaseTest):

    def test_shield_metric_filter(self):
        factory = self.replay_flight_data("test_distribution_shield_metrics")
        p = self.load_policy(
            {
                "name": "ddos-filter",
                "resource": "distribution",
                "filters": [
                    {
                        "type": "shield-metrics",
                        "name": "DDoSDetected",
                        "value": 1,
                        "op": "ge",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_distribution_metric_filter(self):
        factory = self.replay_flight_data("test_distribution_metric_filter")
        p = self.load_policy(
            {
                "name": "requests-filter",
                "resource": "distribution",
                "filters": [
                    {"type": "metrics", "name": "Requests", "value": 3, "op": "ge"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["DomainName"], "d32plmcrnvwzrd.cloudfront.net")

    def test_distribution_set_ssl(self):
        factory = self.replay_flight_data("test_distrbution_set_ssl")

        k = "DefaultCacheBehavior.ViewerProtocolPolicy"

        p = self.load_policy(
            {
                "name": "distribution-set-ssl",
                "resource": "distribution",
                "filters": [
                    {"type": "value", "key": k, "value": "allow-all", "op": "contains"}
                ],
                "actions": [
                    {"type": "set-protocols", "ViewerProtocolPolicy": "https-only"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        expr = jmespath.compile(k)
        r = expr.search(resources[0])
        self.assertTrue("allow-all" in r)

        client = local_session(factory).client("cloudfront")
        resp = client.list_distributions()
        self.assertEqual(
            resp["DistributionList"]["Items"][0]["DefaultCacheBehavior"][
                "ViewerProtocolPolicy"
            ],
            "https-only",
        )

    def test_distribution_custom_origin(self):
        factory = self.replay_flight_data("test_distrbution_custom_origin")

        k = "Origins.Items[].CustomOriginConfig.OriginSslProtocols.Items[]"

        p = self.load_policy(
            {
                "name": "distribution-set-ssl",
                "resource": "distribution",
                "filters": [
                    {"type": "value", "key": k, "value": "TLSv1", "op": "contains"}
                ],
                "actions": [
                    {
                        "type": "set-protocols",
                        "OriginSslProtocols": ["TLSv1.1", "TLSv1.2"],
                        "OriginProtocolPolicy": "https-only",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        expr = jmespath.compile(k)
        r = expr.search(resources[0])
        self.assertTrue("TLSv1" in r)

        client = local_session(factory).client("cloudfront")
        resp = client.list_distributions()
        self.assertEqual(
            resp["DistributionList"]["Items"][0]["Origins"]["Items"][0][
                "CustomOriginConfig"
            ][
                "OriginProtocolPolicy"
            ],
            "https-only",
        )
        self.assertTrue(
            "TLSv1.2" in resp["DistributionList"]["Items"][0]["Origins"]["Items"][0][
                "CustomOriginConfig"
            ][
                "OriginSslProtocols"
            ][
                "Items"
            ]
        )
        self.assertFalse(
            "TLSv1" in resp["DistributionList"]["Items"][0]["Origins"]["Items"][0][
                "CustomOriginConfig"
            ][
                "OriginSslProtocols"
            ][
                "Items"
            ]
        )

    def test_distribution_disable(self):
        factory = self.replay_flight_data("test_distrbution_disable")

        p = self.load_policy(
            {
                "name": "distribution-disable",
                "resource": "distribution",
                "filters": [
                    {
                        "type": "value",
                        "key": "DefaultCacheBehavior.ViewerProtocolPolicy",
                        "value": "allow-all",
                        "op": "contains",
                    }
                ],
                "actions": [{"type": "disable"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Enabled"], True)

        client = local_session(factory).client("cloudfront")
        resp = client.list_distributions()
        self.assertEqual(resp["DistributionList"]["Items"][0]["Enabled"], False)

    def test_distribution_check_s3_origin_missing_bucket(self):
        factory = self.replay_flight_data("test_distribution_check_s3_origin_missing_bucket")

        p = self.load_policy(
            {
                "name": "test_distribution_check_s3_origin_missing_bucket",
                "resource": "distribution",
                "filters": [
                    {
                        "type": "mismatch-s3-origin",
                    }
                ]
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:mismatched-s3-origin'][0], 'c7n-idontexist')

    def test_distribution_tag(self):
        factory = self.replay_flight_data("test_distrbution_tag")

        p = self.load_policy(
            {
                "name": "distribution-tag",
                "resource": "distribution",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "tag", "key": "123", "value": "456"}],
            },
            config=Config.empty(),
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = local_session(factory).client("cloudfront")
        resp = client.list_tags_for_resource(Resource=resources[0]["ARN"])
        self.assertEqual(len(resp["Tags"]["Items"]), 2)

    def test_streaming_distribution_disable(self):
        factory = self.replay_flight_data("test_streaming_distrbution_disable")

        p = self.load_policy(
            {
                "name": "streaming-distribution-disable",
                "resource": "streaming-distribution",
                "filters": [
                    {
                        "type": "value",
                        "key": "S3Origin.OriginAccessIdentity",
                        "value": "",
                    }
                ],
                "actions": [{"type": "disable"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Enabled"], True)

        client = local_session(factory).client("cloudfront")
        resp = client.list_streaming_distributions()
        self.assertEqual(
            resp["StreamingDistributionList"]["Items"][0]["Enabled"], False
        )

    def test_streaming_distribution_tag(self):
        factory = self.replay_flight_data("test_streaming_distrbution_tag")

        p = self.load_policy(
            {
                "name": "streaming-distribution-tag",
                "resource": "streaming-distribution",
                "filters": [{"tag:123": "present"}],
                "actions": [{"type": "tag", "key": "abc", "value": "123"}],
            },
            config=Config.empty(),
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = local_session(factory).client("cloudfront")
        resp = client.list_tags_for_resource(Resource=resources[0]["ARN"])
        self.assertEqual(len(resp["Tags"]["Items"]), 2)

    def test_cloudfront_tagging_multi_region(self):
        factory = self.replay_flight_data("test_cloudfront_multi_region")
        east_p = self.load_policy(
            {
                "name": "cloudfront-tagging-us-east-1",
                "resource": "distribution",
                "filters": [{"tag:tag": "present"}]
            },
            config=Config.empty(region='us-east-1'),
            session_factory=factory,
        )

        west_p = self.load_policy(
            {
                "name": "cloudfront-tagging-us-west-2",
                "resource": "distribution",
                "filters": [{"tag:tag": "present"}]
            },
            config=Config.empty(region='us-west-2'),
            session_factory=factory,
        )

        east_resources = east_p.run()
        west_resources = west_p.run()

        self.assertEqual(east_resources, west_resources)
