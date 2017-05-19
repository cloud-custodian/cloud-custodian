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

import jmespath
from common import BaseTest


class CloudFront(BaseTest):

    def test_distribution_metric_filter(self):
        factory = self.replay_flight_data('test_distribution_metric_filter')
        p = self.load_policy({
            'name': 'requests-filter',
            'resource': 'distribution',
            'filters': [{
                'type': 'metrics',
                'name': 'Requests',
                'value': 3,
                'op': 'ge'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(
            resources[0]['DomainName'], 'd1k7b41j4nj6pa.cloudfront.net')


    def test_distribution_set_ssl(self):
        factory = self.replay_flight_data('test_distrbution_set_ssl')

        k = 'CacheBehaviors.Items[].ViewerProtocolPolicy'

        p = self.load_policy({
            'name': 'distribution-set-ssl',
            'resource': 'distribution',
            'filters': [{
                'type': 'value',
                'key': k,
                'value': 'allow-all',
                'op': 'contains'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        expr = jmespath.compile(k)
        r = expr.search(resources[0])
        self.assertTrue('allow-all' in r)

        p = self.load_policy({
            'name': 'distribution-set-ssl',
            'resource': 'distribution',
            'filters': [{
                'type': 'value',
                'key': k,
                'value': 'allow-all',
                'op': 'contains'
            }],
            'actions': [{
                'type': 'set-ssl'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'distribution-set-ssl',
            'resource': 'distribution',
            'filters': [{
                'type': 'value',
                'key': k,
                'value': 'allow-all',
                'op': 'contains'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)


    def test_distribution_disable(self):
        factory = self.replay_flight_data('test_distrbution_disable')

        p = self.load_policy({
            'name': 'distribution-disable',
            'resource': 'distribution',
            'filters': [{
                'type': 'value',
                'key': 'CacheBehaviors.Items[].ViewerProtocolPolicy',
                'value': 'allow-all',
                'op': 'contains'
            }],
            'actions': [{
                'type': 'disable'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Enabled'], True)

        p = self.load_policy({
            'name': 'distribution-disable',
            'resource': 'distribution',
            'filters': [{
                'type': 'value',
                'key': 'CacheBehaviors.Items[].ViewerProtocolPolicy',
                'value': 'allow-all',
                'op': 'contains'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(resources[0]['Enabled'], False)

    def test_streaming_distribution_disable(self):
        factory = self.replay_flight_data('test_streaming_distrbution_disable')

        p = self.load_policy({
            'name': 'streaming-distribution-disable',
            'resource': 'streaming-distribution',
            'filters': [{
                'type': 'value',
                'key': 'S3Origin.OriginAccessIdentity',
                'value': ''
            }],
            'actions': [{
                'type': 'disable'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Enabled'], True)

        p = self.load_policy({
            'name': 'streaming-distribution-disable',
            'resource': 'streaming-distribution',
            'filters': [{
                'type': 'value',
                'key': 'S3Origin.OriginAccessIdentity',
                'value': ''
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(resources[0]['Enabled'], False)
