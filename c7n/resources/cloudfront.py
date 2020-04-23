# Copyright 2016-2019 Capital One Services, LLC
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
import re

from c7n.actions import BaseAction
from c7n.filters import MetricsFilter, ShieldMetrics, Filter
from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource, TypeInfo
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema, get_retry
from c7n.filters import ValueFilter
from .aws import shape_validate
from c7n.exceptions import PolicyValidationError

from c7n.resources.shield import IsShieldProtected, SetShieldProtection


@resources.register('distribution')
class Distribution(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudfront'
        arn_type = 'distribution'
        enum_spec = ('list_distributions', 'DistributionList.Items', None)
        id = 'Id'
        arn = 'ARN'
        name = 'DomainName'
        date = 'LastModifiedTime'
        dimension = "DistributionId"
        universal_taggable = True
        config_type = "AWS::CloudFront::Distribution"
        # Denotes this resource type exists across regions
        global_resource = True

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeDistribution(self)
        return super(Distribution, self).get_source(source_type)


class DescribeDistribution(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('streaming-distribution')
class StreamingDistribution(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudfront'
        arn_type = 'streaming-distribution'
        enum_spec = ('list_streaming_distributions',
                     'StreamingDistributionList.Items',
                     None)
        id = 'Id'
        arn = 'ARN'
        name = 'DomainName'
        date = 'LastModifiedTime'
        dimension = "DistributionId"
        universal_taggable = True
        config_type = "AWS::CloudFront::StreamingDistribution"

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeStreamingDistribution(self)
        return super(StreamingDistribution, self).get_source(source_type)


class DescribeStreamingDistribution(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, resources)


Distribution.filter_registry.register('shield-metrics', ShieldMetrics)
Distribution.filter_registry.register('shield-enabled', IsShieldProtected)
Distribution.action_registry.register('set-shield', SetShieldProtection)


@Distribution.filter_registry.register('metrics')
@StreamingDistribution.filter_registry.register('metrics')
class DistributionMetrics(MetricsFilter):
    """Filter cloudfront distributions based on metric values

    :example:

    .. code-block:: yaml

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


@Distribution.filter_registry.register('waf-enabled')
class IsWafEnabled(Filter):
    # useful primarily to use the same name across accounts, else webaclid
    # attribute works as well

    schema = type_schema(
        'waf-enabled', **{
            'web-acl': {'type': 'string'},
            'state': {'type': 'boolean'}})

    permissions = ('waf:ListWebACLs',)

    def process(self, resources, event=None):
        target_acl = self.data.get('web-acl')
        wafs = self.manager.get_resource_manager('waf').resources()
        waf_name_id_map = {w['Name']: w['WebACLId'] for w in wafs}
        target_acl = self.data.get('web-acl')
        target_acl_id = waf_name_id_map.get(target_acl, target_acl)

        if target_acl_id and target_acl_id not in waf_name_id_map.values():
            raise ValueError("invalid web acl: %s" % (target_acl_id))

        state = self.data.get('state', False)
        results = []
        for r in resources:
            if state and target_acl_id is None and r.get('WebACLId'):
                results.append(r)
            elif not state and target_acl_id is None and not r.get('WebACLId'):
                results.append(r)
            elif state and target_acl_id and r['WebACLId'] == target_acl_id:
                results.append(r)
            elif not state and target_acl_id and r['WebACLId'] != target_acl_id:
                results.append(r)
        return results


@Distribution.filter_registry.register('distribution-config')
class DistributionConfig(ValueFilter):
    """Check for Cloudfront distribution config values

    :example:

    .. code-block:: yaml

            policies:
              - name: logging-enabled
                resource: distribution
                filters:
                  - type: distribution-config
                    key: Logging.Enabled
                    value: true
   """

    schema = type_schema('distribution-config', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('cloudfront:GetDistributionConfig',)
    annotation_key = 'c7n:distribution-config'
    annotate = False

    def process(self, resources, event=None):

        self.augment([r for r in resources if self.annotation_key not in r])
        return super().process(resources, event)

    def augment(self, resources):

        client = local_session(self.manager.session_factory).client(
            'cloudfront', region_name=self.manager.config.region)

        for r in resources:
            try:
                r[self.annotation_key] = client.get_distribution_config(Id=r['Id']) \
                    .get('DistributionConfig')
            except (client.exceptions.NoSuchDistribution):
                r[self.annotation_key] = {}
            except Exception as e:
                self.log.warning(
                    "Exception trying to get Distribution Config: %s error: %s",
                    r['ARN'], e)
                raise e

    def __call__(self, r):
        return super(DistributionConfig, self).__call__(r[self.annotation_key])


@Distribution.filter_registry.register('mismatch-s3-origin')
class MismatchS3Origin(Filter):
    """Check for existence of S3 bucket referenced by Cloudfront,
       and verify whether owner is different from Cloudfront account owner.

    :example:

    .. code-block:: yaml

            policies:
              - name: mismatch-s3-origin
                resource: distribution
                filters:
                  - type: mismatch-s3-origin
                    check_custom_origins: true
   """

    s3_prefix = re.compile(r'.*(?=\.s3(-.*)?\.amazonaws.com)')
    s3_suffix = re.compile(r'^([^.]+\.)?s3(-.*)?\.amazonaws.com')

    schema = type_schema(
        'mismatch-s3-origin',
        check_custom_origins={'type': 'boolean'})

    permissions = ('s3:ListAllMyBuckets',)
    retry = staticmethod(get_retry(('Throttling',)))

    def is_s3_domain(self, x):
        bucket_match = self.s3_prefix.match(x['DomainName'])

        if bucket_match:
            return bucket_match.group()

        domain_match = self.s3_suffix.match(x['DomainName'])

        if domain_match:
            value = x['OriginPath']

            if value.startswith('/'):
                value = value.replace("/", "", 1)

            return value

        return None

    def process(self, resources, event=None):
        results = []

        s3_client = local_session(self.manager.session_factory).client(
            's3', region_name=self.manager.config.region)

        buckets = {b['Name'] for b in s3_client.list_buckets()['Buckets']}

        for r in resources:
            r['c7n:mismatched-s3-origin'] = []
            for x in r['Origins']['Items']:
                if 'S3OriginConfig' in x:
                    bucket_match = self.s3_prefix.match(x['DomainName'])
                    if bucket_match:
                        target_bucket = self.s3_prefix.match(x['DomainName']).group()
                elif 'CustomOriginConfig' in x and self.data.get('check_custom_origins'):
                    target_bucket = self.is_s3_domain(x)

                if target_bucket is not None and target_bucket not in buckets:
                    self.log.debug("Bucket %s not found in distribution %s hosting account."
                                   % (target_bucket, r['Id']))
                    r['c7n:mismatched-s3-origin'].append(target_bucket)
                    results.append(r)

        return results


@Distribution.action_registry.register('set-waf')
class SetWaf(BaseAction):
    permissions = ('cloudfront:UpdateDistribution', 'waf:ListWebACLs')
    schema = type_schema(
        'set-waf', required=['web-acl'], **{
            'web-acl': {'type': 'string'},
            'force': {'type': 'boolean'},
            'state': {'type': 'boolean'}})

    retry = staticmethod(get_retry(('Throttling',)))

    def process(self, resources):
        wafs = self.manager.get_resource_manager('waf').resources()
        waf_name_id_map = {w['Name']: w['WebACLId'] for w in wafs}
        target_acl = self.data.get('web-acl')
        target_acl_id = waf_name_id_map.get(target_acl, target_acl)

        if target_acl_id not in waf_name_id_map.values():
            raise ValueError("invalid web acl: %s" % (target_acl_id))

        client = local_session(self.manager.session_factory).client(
            'cloudfront')
        force = self.data.get('force', False)

        for r in resources:
            if r.get('WebACLId') and not force:
                continue
            if r.get('WebACLId') == target_acl_id:
                continue
            result = client.get_distribution_config(Id=r['Id'])
            config = result['DistributionConfig']
            config['WebACLId'] = target_acl_id
            self.retry(
                client.update_distribution,
                Id=r['Id'], DistributionConfig=config, IfMatch=result['ETag'])


@Distribution.action_registry.register('disable')
class DistributionDisableAction(BaseAction):
    """Action to disable a Distribution

    :example:

    .. code-block:: yaml

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
    permissions = ("cloudfront:GetDistributionConfig",
                   "cloudfront:UpdateDistribution",)

    def process(self, distributions):
        client = local_session(
            self.manager.session_factory).client(self.manager.get_model().service)

        for d in distributions:
            self.process_distribution(client, d)

    def process_distribution(self, client, distribution):
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

    .. code-block:: yaml

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

    permissions = ("cloudfront:GetStreamingDistributionConfig",
                   "cloudfront:UpdateStreamingDistribution",)

    def process(self, distributions):
        client = local_session(
            self.manager.session_factory).client(self.manager.get_model().service)
        for d in distributions:
            self.process_distribution(client, d)

    def process_distribution(self, client, distribution):
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

    .. code-block:: yaml

            policies:
              - name: distribution-set-ssl
                resource: distribution
                filters:
                  - type: value
                    key: CacheBehaviors.Items[].ViewerProtocolPolicy
                    value: allow-all
                    op: contains
                actions:
                  - type: set-protocols
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

    permissions = ("cloudfront:GetDistributionConfig",
                   "cloudfront:UpdateDistribution",)

    def process(self, distributions):
        client = local_session(self.manager.session_factory).client(
            self.manager.get_model().service)
        for d in distributions:
            self.process_distribution(client, d)

    def process_distribution(self, client, distribution):
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


@Distribution.action_registry.register('set-attributes')
class DistributionUpdateAction(BaseAction):
    """Action to update the attributes of a distribution

    :example:

    .. code-block:: yaml

        policies:
        - name: enforce-distribution-logging
          resource: distribution
          filters:
            - type: value
              key: "Logging.Enabled"
              value: null
          actions:
            - type: set-attributes
              attributes:
                Comment: ""
                Enabled: true
                Logging:
                    Enabled: true
                    IncludeCookies: false
                    Bucket: 'test-enable-logging-c7n.s3.amazonaws.com'
                    Prefix: ''
    """
    schema = type_schema('set-attributes',
                        attributes={"type": "object"},
                        required=('attributes',))

    permissions = ("cloudfront:UpdateDistribution",
                   "cloudfront:GetDistributionConfig",)
    shape = 'UpdateDistributionRequest'

    def validate(self):
        attrs = dict(self.data.get('attributes'))
        if attrs.get('CallerReference'):
            raise PolicyValidationError('CallerReference field cannot be updated')

        # Set default values for required fields if they are not present
        attrs["CallerReference"] = ""
        self.set_required_update_fields(attrs)
        request = {
            "DistributionConfig": attrs,
            "Id": "sample_id",
            "IfMatch": "sample_string",
        }
        return shape_validate(request, self.shape, 'cloudfront')

    def set_required_update_fields(self, config):
        if 'Origins' not in config:
            config["Origins"] = {
                "Quantity": 0,
                "Items": [
                    {
                        "Id": "",
                        "DomainName": ""
                    }
                ],
            }
        if 'DefaultCacheBehavior' not in config:
            config["DefaultCacheBehavior"] = {
                "TargetOriginId": "",
                "ForwardedValues": {
                    "QueryString": True,
                    "Cookies": {
                        "Forward": ""
                    }
                },
                "TrustedSigners": {
                    "Enabled": True,
                    "Quantity": 0,
                },
                "ViewerProtocolPolicy": "",
                "MinTTL": 0
            }

    def process(self, distributions):
        client = local_session(self.manager.session_factory).client(
            self.manager.get_model().service)
        for d in distributions:
            self.process_distribution(client, d)

    def process_distribution(self, client, distribution):
        try:
            res = client.get_distribution_config(
                Id=distribution[self.manager.get_model().id])
            config = res['DistributionConfig']
            updatedConfig = {**config, **self.data['attributes']}
            self.set_required_update_fields(updatedConfig)
            if config == updatedConfig:
                return
            res = client.update_distribution(
                Id=distribution[self.manager.get_model().id],
                IfMatch=res['ETag'],
                DistributionConfig=updatedConfig
            )
        except (client.exceptions.NoSuchResource, client.exceptions.NoSuchDistribution):
            pass
        except Exception as e:
            self.log.warning(
                "Exception trying to update Distribution: %s error: %s",
                distribution['ARN'], e)
            raise e
