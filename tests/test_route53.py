# Copyright 2016 Capital One Services, LLC
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

import logging

from .common import BaseTest
from c7n.resources.route53 import HostedZone


class Route53HostedZoneTest(BaseTest):

    def test_route53_hostedzone_tag(self):
        session_factory = self.replay_flight_data('test_route53_hostedzone_tag')

        p = self.load_policy({
            'name': 'hostedzone-tag-records',
            'resource': 'hostedzone',
            'filters': [
                {
                    'type': 'value',
                    'key': 'ResourceRecordSetCount',
                    'value': 2,
                    'op': 'gte'
                }
            ],
            'actions': [
                {
                    'type': 'tag',
                    'key': 'abc',
                    'value': 'xyz'
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('route53')
        _id = resources[0]['Id'].split("/")[-1]
        tags = client.list_tags_for_resource(
            ResourceType = "hostedzone",
            ResourceId = _id
        )
        self.assertEqual(len(tags['ResourceTagSet']['Tags']), 1)
        self.assertTrue('abc' in tags['ResourceTagSet']['Tags'][0].values())

    def test_route53_hostedzone_tag_exception(self):
        output = self.capture_logging(level=logging.DEBUG)
        # intentionally cause error to be thrown by sending wrong arn
        def generate_arn(*args):
            return 'arn:aws:route53:::hostedzone/Z148QEXAMPLE8V'
        self.patch(HostedZone, 'generate_arn', generate_arn)

        session_factory = self.replay_flight_data('test_route53_hostedzone_tag_exception')
        p = self.load_policy({
            'name': 'hostedzone-tag-records',
            'resource': 'hostedzone',
            'filters': [
                {
                    'type': 'value',
                    'key': 'ResourceRecordSetCount',
                    'value': 2,
                    'op': 'gte'
                }
            ],
            'actions': [
                {
                    'type': 'tag',
                    'key': 'abc',
                    'value': 'xyz'
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        self.assertTrue(("Resource:arn:aws:route53:::hostedzone/Z148QEXAMPLE8V "
                         "ErrorCode:NoSuchHostedZone StatusCode:404 "
                         "ErrorMessage:No hosted zone "
                         "found with ID: Z148QEXAMPLE8V") in output.getvalue())

    def test_route53_hostedzone_untag(self):
        session_factory = self.replay_flight_data('test_route53_hostedzone_untag')

        p = self.load_policy({
            'name': 'hostedzone-untag-records',
            'resource': 'hostedzone',
            'filters': [
                {
                    'tag:abc': 'present',
                }
            ],
            'actions': [
                {
                    'type': 'remove-tag',
                    'tags': ['abc']
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('route53')
        _id = resources[0]['Id'].split("/")[-1]
        tags = client.list_tags_for_resource(
            ResourceType = "hostedzone",
            ResourceId = _id
        )
        self.assertEqual(len(tags['ResourceTagSet']['Tags']), 0)

    def test_route53_hostedzone_markop(self):
        session_factory = self.replay_flight_data('test_route53_hostedzone_markop')

        p = self.load_policy({
            'name': 'hostedzone-markop-records',
            'resource': 'hostedzone',
            'filters': [
                {
                    'tag:abc': 'present',
                }
            ],
            'actions': [
                {
                    'type': 'mark-for-op',
                    'op': 'notify',
                    'days': 4
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('route53')
        _id = resources[0]['Id'].split("/")[-1]
        tags = client.list_tags_for_resource(
            ResourceType = "hostedzone",
            ResourceId = _id
        )
        self.assertEqual(len(tags['ResourceTagSet']['Tags']), 2)
        self.assertTrue('abc' in tags['ResourceTagSet']['Tags'][0].values())


class Route53HealthCheckTest(BaseTest):

    def test_route53_healthcheck_tag(self):
        session_factory = self.replay_flight_data('test_route53_healthcheck_tag')

        p = self.load_policy({
            'name': 'healthcheck-tag-records',
            'resource': 'healthcheck',
            'filters': [
                {
                    'type': 'value',
                    'key': "HealthCheckConfig.FailureThreshold",
                    'value': 3,
                    'op': 'gte'
                }
            ],
            'actions': [
                {
                    'type': 'tag',
                    'key': 'abc',
                    'value': 'xyz'
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('route53')
        tags = client.list_tags_for_resource(
            ResourceType = "healthcheck",
            ResourceId = resources[0]['Id']
        )
        self.assertEqual(len(tags['ResourceTagSet']['Tags']), 2)
        self.assertTrue('abc' in tags['ResourceTagSet']['Tags'][0].values())

    def test_route53_healthcheck_untag(self):
        session_factory = self.replay_flight_data('test_route53_healthcheck_untag')

        p = self.load_policy({
            'name': 'healthcheck-untag-records',
            'resource': 'healthcheck',
            'filters': [
                {
                    'tag:abc': 'present',
                }
            ],
            'actions': [
                {
                    'type': 'remove-tag',
                    'tags': ['abc']
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('route53')
        tags = client.list_tags_for_resource(
            ResourceType = "healthcheck",
            ResourceId = resources[0]['Id']
        )
        self.assertEqual(len(tags['ResourceTagSet']['Tags']), 1) # Name is a tag
        self.assertTrue('Name' in tags['ResourceTagSet']['Tags'][0].values())

    def test_route53_healthcheck_markop(self):
        session_factory = self.replay_flight_data('test_route53_healthcheck_markop')

        p = self.load_policy({
            'name': 'healthcheck-markop-records',
            'resource': 'healthcheck',
            'filters': [
                {
                    'tag:abc': 'present',
                }
            ],
            'actions': [
                {
                    'type': 'mark-for-op',
                    'op': 'notify',
                    'days': 4
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('route53')
        _id = resources[0]['Id'].split("/")[-1]
        tags = client.list_tags_for_resource(
            ResourceType = "healthcheck",
            ResourceId = _id
        )
        self.assertEqual(len(tags['ResourceTagSet']['Tags']), 3)
        self.assertTrue('maid_status' in tags['ResourceTagSet']['Tags'][1].values())


class Route53DomainTest(BaseTest):

    def test_route53_domain_auto_renew(self):
        session_factory = self.replay_flight_data('test_route53_domain')
        p = self.load_policy({
             'name': 'r53domain-auto-renew',
             'resource': 'r53domain',
             'filters': [
                {
                'type': 'value',
                'key': 'AutoRenew',
                'value': False
                }
                ]},
             session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_route53_domain_transfer_lock(self):
        session_factory = self.replay_flight_data('test_route53_domain')
        p = self.load_policy({
             'name': 'r53domain-transfer-lock',
             'resource': 'r53domain',
             'filters': [
                {
                'type': 'value',
                'key': 'TransferLock',
                'value': False
                }
                ]},
             session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
