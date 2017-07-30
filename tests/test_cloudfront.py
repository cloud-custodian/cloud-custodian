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
from .common import BaseTest
from c7n.utils import local_session


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
                'type': 'set-protocols',
                'ViewerProtocolPolicy': 'https-only'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = local_session(factory).client('cloudfront')
        resp = client.list_distributions()
        self.assertEqual(
            resp['DistributionList']['Items'][0]['CacheBehaviors']['Items'][0]['ViewerProtocolPolicy'],
            'https-only')


    def test_distribution_custom_origin(self):
        factory = self.replay_flight_data('test_distrbution_custom_origin')

        k = 'Origins.Items[].CustomOriginConfig.OriginSslProtocols.Items[]'

        p = self.load_policy({
            'name': 'distribution-set-ssl',
            'resource': 'distribution',
            'filters': [{
                'type': 'value',
                'key': k,
                'value': 'TLSv1',
                'op': 'contains'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        expr = jmespath.compile(k)
        r = expr.search(resources[0])
        self.assertTrue('TLSv1.1' in r)

        p = self.load_policy({
            'name': 'distribution-set-ssl',
            'resource': 'distribution',
            'filters': [{
                'type': 'value',
                'key': k,
                'value': 'TLSv1',
                'op': 'contains'
            }],
            'actions': [{
                'type': 'set-protocols',
                'OriginSslProtocols': ['TLSv1.1','TLSv1.2'],
                'OriginProtocolPolicy': 'https-only'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = local_session(factory).client('cloudfront')
        resp = client.list_distributions()
        self.assertEqual(
            resp['DistributionList']['Items'][0]['Origins']['Items'][0]['CustomOriginConfig']['OriginProtocolPolicy'],
            'https-only')
        self.assertTrue('TLSv1.2' in
            resp['DistributionList']['Items'][0]['Origins']['Items'][0]['CustomOriginConfig']['OriginSslProtocols']['Items'])


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

        client = local_session(factory).client('cloudfront')
        resp = client.list_distributions()
        self.assertEqual(resp['DistributionList']['Items'][0]['Enabled'], False)


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

        client = local_session(factory).client('cloudfront')
        resp = client.list_streaming_distributions()
        self.assertEqual(resp['StreamingDistributionList']['Items'][0]['Enabled'], False)
