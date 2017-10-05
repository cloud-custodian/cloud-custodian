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

import functools

from c7n.actions import BaseAction
from c7n.filters import MetricsFilter, ShieldMetrics
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import universal_augment
from c7n.utils import generate_arn, local_session, type_schema

from c7n.resources.shield import IsShieldProtected, SetShieldProtection


@resources.register('distribution')
class Distribution(QueryResourceManager):

    class resource_type(object):
        service = 'cloudfront'
        type = 'distribution'
        enum_spec = ('list_distributions', 'DistributionList.Items', None)
        id = 'Id'
        name = 'DomainName'
        date = 'LastModifiedTime'
        dimension = "DistributionId"
        universal_taggable = True
        filter_name = None

    augment = universal_augment

    def get_arn(self, r):
        return r['ARN']

    @property
    def generate_arn(self):
        """ Generates generic arn if ID is not already arn format.
        """
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                self.get_model().service,
                account_id=self.account_id,
                resource_type=self.get_model().type,
                separator='/')
        return self._generate_arn


@resources.register('streaming-distribution')
class StreamingDistribution(QueryResourceManager):

    class resource_type(object):
        service = 'cloudfront'
        type = 'streaming-distribution'
        enum_spec = ('list_streaming_distributions',
                     'StreamingDistributionList.Items',
                     None)
        id = 'Id'
        name = 'DomainName'
        date = 'LastModifiedTime'
        dimension = "DistributionId"
        universal_taggable = True
        filter_name = None

    augment = universal_augment

    def get_arn(self, r):
        return r['ARN']

    @property
    def generate_arn(self):
        """ Generates generic arn if ID is not already arn format.
        """
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                self.get_model().service,
                account_id=self.account_id,
                resource_type=self.get_model().type,
                separator='/')
        return self._generate_arn


Distribution.filter_registry.register('shield-metrics', ShieldMetrics)
Distribution.filter_registry.register('shield-enabled', IsShieldProtected)
Distribution.action_registry.register('set-shield', SetShieldProtection)


@Distribution.filter_registry.register('metrics')
@StreamingDistribution.filter_registry.register('metrics')
class DistributionMetrics(MetricsFilter):
    """Filter cloudfront distributions based on metric values

    :example:

        .. code-block: yaml

            policies:
              - name: cloudfront-distribution-errors
                resource: distribution
                filters:
                  - type: metrics
                    name: Requests
                    value: 3
                    op: ge
    """

    def get_dimensions(self, resource):
        return [{'Name': self.model.dimension,
                 'Value': resource[self.model.id]},
                {'Name': 'Region', 'Value': 'Global'}]


@Distribution.action_registry.register('disable')
class DistributionDisableAction(BaseAction):
    """Action to disable a Distribution

    :example:

        .. code-block: yaml

            policies:
              - name: distribution-delete
                resource: distribution
                filters:
                  - type: value
                    key: CacheBehaviors.Items[].ViewerProtocolPolicy
                    value: allow-all
                    op: contains
                actions:
                  - type: disable
    """
    schema = type_schema('disable')
    permissions = ("distribution:GetDistributionConfig",
                   "distribution:UpdateDistribution",)

    def process(self, distributions):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_distribution, distributions))

    def process_distribution(self, distribution):
        client = local_session(
            self.manager.session_factory).client(self.manager.get_model().service)
        try:
            res = client.get_distribution_config(
                Id=distribution[self.manager.get_model().id])
            res['DistributionConfig']['Enabled'] = False
            res = client.update_distribution(
                Id=distribution[self.manager.get_model().id],
                IfMatch=res['ETag'],
                DistributionConfig=res['DistributionConfig']
            )
        except Exception as e:
            self.log.warning(
                "Exception trying to disable Distribution: %s error: %s",
                distribution['ARN'], e)
            return


@StreamingDistribution.action_registry.register('disable')
class StreamingDistributionDisableAction(BaseAction):
    """Action to disable a Streaming Distribution

    :example:

        .. code-block: yaml

            policies:
              - name: streaming-distribution-delete
                resource: streaming-distribution
                filters:
                  - type: value
                    key: S3Origin.OriginAccessIdentity
                    value: ''
                actions:
                  - type: disable
    """
    schema = type_schema('disable')

    permissions = ("streaming-distribution:GetStreamingDistributionConfig",
                   "streaming-distribution:UpdateStreamingDistribution",)

    def process(self, distributions):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_distribution, distributions))

    def process_distribution(self, distribution):
        client = local_session(
            self.manager.session_factory).client(self.manager.get_model().service)
        try:
            res = client.get_streaming_distribution_config(
                Id=distribution[self.manager.get_model().id])
            res['StreamingDistributionConfig']['Enabled'] = False
            res = client.update_streaming_distribution(
                Id=distribution[self.manager.get_model().id],
                IfMatch=res['ETag'],
                StreamingDistributionConfig=res['StreamingDistributionConfig']
            )
        except Exception as e:
            self.log.warning(
                "Exception trying to disable Distribution: %s error: %s",
                distribution['ARN'], e)
            return


@Distribution.action_registry.register('set-protocols')
class DistributionSSLAction(BaseAction):
    """Action to set mandatory https-only on a Distribution

    :example:

        .. code-block: yaml

            policies:
              - name: distribution-set-ssl
                resource: distribution
                filters:
                  - type: value
                    key: CacheBehaviors.Items[].ViewerProtocolPolicy
                    value: allow-all
                    op: contains
                actions:
                  - type: set-ssl
                    ViewerProtocolPolicy: https-only
    """
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['set-protocols']},
            'OriginProtocolPolicy': {
                'enum': ['http-only', 'match-viewer', 'https-only']
            },
            'OriginSslProtocols': {
                'type': 'array',
                'items': {'enum': ['SSLv3', 'TLSv1', 'TLSv1.1', 'TLSv1.2']}
            },
            'ViewerProtocolPolicy': {
                'enum': ['allow-all', 'https-only', 'redirect-to-https']
            }
        }
    }

    permissions = ("distribution:GetDistributionConfig",
                   "distribution:UpdateDistribution",)

    def process(self, distributions):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_distribution, distributions))

    def process_distribution(self, distribution):
        client = local_session(
            self.manager.session_factory).client(self.manager.get_model().service)
        try:
            res = client.get_distribution_config(
                Id=distribution[self.manager.get_model().id])
            etag = res['ETag']
            dc = res['DistributionConfig']

            for item in dc['CacheBehaviors'].get('Items', []):
                item['ViewerProtocolPolicy'] = self.data.get(
                    'ViewerProtocolPolicy',
                    item['ViewerProtocolPolicy'])
            dc['DefaultCacheBehavior']['ViewerProtocolPolicy'] = self.data.get(
                'ViewerProtocolPolicy',
                dc['DefaultCacheBehavior']['ViewerProtocolPolicy'])

            for item in dc['Origins'].get('Items', []):
                if item.get('CustomOriginConfig', False):
                    item['CustomOriginConfig']['OriginProtocolPolicy'] = self.data.get(
                        'OriginProtocolPolicy',
                        item['CustomOriginConfig']['OriginProtocolPolicy'])

                    item['CustomOriginConfig']['OriginSslProtocols']['Items'] = self.data.get(
                        'OriginSslProtocols',
                        item['CustomOriginConfig']['OriginSslProtocols']['Items'])

                    item['CustomOriginConfig']['OriginSslProtocols']['Quantity'] = len(
                        item['CustomOriginConfig']['OriginSslProtocols']['Items'])

            res = client.update_distribution(
                Id=distribution[self.manager.get_model().id],
                IfMatch=etag,
                DistributionConfig=dc
            )
        except Exception as e:
            self.log.warning(
                "Exception trying to force ssl on Distribution: %s error: %s",
                distribution['ARN'], e)
            return
