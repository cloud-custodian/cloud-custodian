# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters import MetricsFilter, ShieldMetrics, Filter
from c7n.manager import resources
from c7n.query import ConfigSource, QueryResourceManager, DescribeSource, TypeInfo
from c7n.tags import universal_augment
from c7n.utils import local_session, merge_dict, type_schema, get_retry
from c7n.filters import ValueFilter, WafV2FilterBase
from .aws import shape_validate
from c7n.exceptions import PolicyValidationError

from c7n.resources.aws import Arn
from c7n.resources.shield import IsShieldProtected, SetShieldProtection
from c7n.resources.securityhub import PostFinding


class DescribeDistribution(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, resources)

    def get_resources(self, ids, cache=True):
        results = []
        distribution_ids = []
        for i in ids:
            # if we get cloudfront distribution arn, we pick distribution id
            if i.startswith('arn:'):
                distribution_ids.append(Arn.parse(i).resource)
            else:
                distribution_ids.append(i)
        if distribution_ids:
            results = super().get_resources(distribution_ids, cache)
        return results


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
        cfn_type = config_type = "AWS::CloudFront::Distribution"
        # Denotes this resource type exists across regions
        global_resource = True
        permission_augment = ("cloudfront:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeDistribution,
        'config': ConfigSource
    }


class DescribeStreamingDistribution(DescribeSource):

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
        cfn_type = config_type = "AWS::CloudFront::StreamingDistribution"

    source_mapping = {
        'describe': DescribeStreamingDistribution,
        'config': ConfigSource
    }


@resources.register("origin-access-control")
class OriginAccessControl(QueryResourceManager):
    class resource_type(TypeInfo):
        service = "cloudfront"
        arn_type = "origin-access-control"
        enum_spec = (
            "list_origin_access_controls",
            "OriginAccessControlList.Items",
            None,
        )
        id = "Id"
        description = "Description"
        name = "Name"
        signing_protocol = "SigningProtocol"
        signing_behavior = "SigningBehavior"
        origin_type = "OriginAccessControlOriginType"
        cfn_type = "AWS::CloudFront::OriginAccessControl"


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
    """Filter CloudFront distribution by waf-regional web-acl

    :example:

    .. code-block:: yaml

            policies:
              - name: filter-distribution-waf
                resource: distribution
                filters:
                  - type: waf-enabled
                    state: false
                    web-acl: test
    """
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
            elif not state and target_acl_id is None and (not r.get('WebACLId') or
                    r.get('WebACLId') not in waf_name_id_map.values()):
                results.append(r)
            elif state and target_acl_id and r['WebACLId'] == target_acl_id:
                results.append(r)
            elif not state and target_acl_id and r['WebACLId'] != target_acl_id:
                results.append(r)
        return results


@Distribution.filter_registry.register('wafv2-enabled')
class IsWafV2Enabled(WafV2FilterBase):
    """Filter CloudFront distribution by wafv2 web-acl

    :example:

    .. code-block:: yaml

            policies:
              - name: filter-distribution-wafv2
                description: |
                  match resources that are NOT associated with any wafV2 web-acls
                resource: distribution
                filters:
                  - type: wafv2-enabled
                    state: false

              - name: filter-distribution-wafv2-specific-acl
                description: |
                  match resources that are NOT associated with wafV2's testv2 web-acl
                resource: distribution
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: testv2

              - name: filter-distribution-wafv2-regex
                description: |
                  match resources that are NOT associated with specified
                  wafV2 web-acl regex
                resource: distribution
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: .*FMManagedWebACLV2-?FMS-.*
    """

    def get_associated_web_acl(self, resource):
        # for WAFv2 Cloudfront stores the ARN of the WebACL even though the attribute is 'WebACLId'
        return self.get_web_acl_by_arn(resource.get('WebACLId'), scope='CLOUDFRONT')


class BaseDistributionConfig(ValueFilter):
    schema = type_schema('distribution-config', rinherit=ValueFilter.schema)
    schema_alias = False
    annotation_key = 'c7n:distribution-config'
    annotate = False

    def process(self, resources, event=None):

        self.augment([r for r in resources if self.annotation_key not in r])
        return super().process(resources, event)

    def __call__(self, r):
        return super(BaseDistributionConfig, self).__call__(r[self.annotation_key])


@Distribution.filter_registry.register('distribution-config')
class DistributionConfig(BaseDistributionConfig):
    """Check for Cloudfront distribution config values

    :example:

    .. code-block:: yaml

            policies:
              - name: logging-enabled
                resource: distribution
                filters:
                  - type: distribution-config
                    key: Logging.Enabled
                    value: False
   """
    permissions = ('cloudfront:GetDistributionConfig',)

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


@StreamingDistribution.filter_registry.register('distribution-config')
class StreamingDistributionConfig(BaseDistributionConfig):
    """Check for Cloudfront streaming distribution config values

    :example:

    .. code-block:: yaml

            policies:
              - name: streaming-distribution-logging-enabled
                resource: streaming-distribution
                filters:
                  - type: distribution-config
                    key: Logging.Enabled
                    value: true
   """
    permissions = ('cloudfront:GetStreamingDistributionConfig',)

    def augment(self, resources):

        client = local_session(self.manager.session_factory).client(
            'cloudfront', region_name=self.manager.config.region)

        for r in resources:
            try:
                r[self.annotation_key] = client.get_streaming_distribution_config(Id=r['Id']) \
                    .get('StreamingDistributionConfig')
            except (client.exceptions.NoSuchStreamingDistribution):
                r[self.annotation_key] = {}
            except Exception as e:
                self.log.warning(
                    "Exception trying to get Streaming Distribution Config: %s error: %s",
                    r['ARN'], e)
                raise e


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

    s3_prefix = re.compile(r'.*(?=\.s3(-.*)?(\..*-\d)?\.amazonaws.com)')
    s3_suffix = re.compile(r'^([^.]+\.)?s3(-.*)?(\..*-\d)?\.amazonaws.com')

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


@Distribution.action_registry.register('post-finding')
class DistributionPostFinding(PostFinding):

    resource_type = 'AwsCloudFrontDistribution'

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        origins = r['Origins']

        payload.update(self.filter_empty({
            'DomainName': r['DomainName'],
            "WebAclId": r.get('WebACLId'),
            'LastModifiedTime': r['LastModifiedTime'].isoformat(),
            'Status': r['Status'],
            'Logging': self.filter_empty(r.get('Logging', {})),
            'Origins': {
                'Items': [
                    {
                        # Extract a subset of origin item keys,
                        # only if they're non-empty.
                        #
                        # The full item can be large and noisy, and
                        # empty string values (notably for OriginPath)
                        # will fail validation.
                        k: o[k]
                        for k in self.filter_empty(o)
                        if k in ('Id', 'OriginPath', 'DomainName')
                    }
                    for o in origins['Items']
                ]
            }
        }))

        return envelope


@Distribution.action_registry.register('set-waf')
class SetWaf(BaseAction):
    """Enable waf protection on CloudFront distribution.

    :example:

    .. code-block:: yaml

            policies:
              - name: set-waf-for-cloudfront
                resource: distribution
                filters:
                  - type: waf-enabled
                    state: false
                    web-acl: test
                actions:
                  - type: set-waf
                    state: true
                    force: true
                    web-acl: test

              - name: disassociate-waf-associate-wafv2-cf
                resource: distribution
                filters:
                  - type: waf-enabled
                    state: true
                actions:
                  - type: set-wafv2
                    state: true
                    force: true
                    web-acl: testv2

    """
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
            try:
                result = client.get_distribution_config(Id=r['Id'])
                config = result['DistributionConfig']
                config['WebACLId'] = target_acl_id
                self.retry(
                    client.update_distribution,
                    Id=r['Id'], DistributionConfig=config, IfMatch=result['ETag'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidArgument':
                    # CloudFront distributions with pricing plans cannot have their
                    # WAF changed. Skip these resources gracefully.
                    # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/flat-rate-pricing-plan.html
                    if 'pricing plan subscription' in str(e):
                        self.log.warning(
                            "Skipping WAF update for distribution %s: distribution has a "
                            "CloudFront pricing plan subscription which requires a web ACL",
                            r['Id'])
                        continue
                raise


@Distribution.action_registry.register('set-wafv2')
class SetWafv2(BaseAction):
    """Enable wafv2 protection on CloudFront distribution.

    :example:

    .. code-block:: yaml

            policies:
              - name: set-wafv2-for-cloudfront
                resource: distribution
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: testv2
                actions:
                  - type: set-wafv2
                    state: true
                    force: true
                    web-acl: testv2

              - name: disassociate-wafv2-associate-waf-cf
                resource: distribution
                filters:
                  - type: wafv2-enabled
                    state: true
                actions:
                  - type: set-waf
                    state: true
                    force: true
                    web-acl: test

            policies:
              - name: set-wafv2-for-cloudfront-regex
                resource: distribution
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: .*FMManagedWebACLV2-?FMS-.*
                actions:
                  - type: set-wafv2
                    state: true
                    web-acl: FMManagedWebACLV2-?FMS-TestWebACL
    """
    permissions = ('cloudfront:UpdateDistribution', 'wafv2:ListWebACLs')
    schema = type_schema(
        'set-wafv2', **{
            'web-acl': {'type': 'string'},
            'force': {'type': 'boolean'},
            'state': {'type': 'boolean'}})

    retry = staticmethod(get_retry(('Throttling',)))

    def process(self, resources):
        query = {'Scope': 'CLOUDFRONT'}
        wafs = self.manager.get_resource_manager('wafv2').resources(query, augment=False)
        waf_name_id_map = {w['Name']: w['ARN'] for w in wafs}
        state = self.data.get('state', True)

        target_acl_id = ''
        if state:
            target_acl = self.data.get('web-acl', '')
            target_acl_ids = [v for k, v in waf_name_id_map.items() if
                              re.match(target_acl, k)]
            if len(target_acl_ids) != 1:
                raise ValueError(f'{target_acl} matching to none or '
                                 f'multiple webacls')
            target_acl_id = target_acl_ids[0]

        client = local_session(self.manager.session_factory).client('cloudfront')
        force = self.data.get('force', False)

        for r in resources:
            if r.get('WebACLId') and not force:
                continue
            if r.get('WebACLId') == target_acl_id:
                continue
            try:
                result = client.get_distribution_config(Id=r['Id'])
                config = result['DistributionConfig']
                config['WebACLId'] = target_acl_id
                self.retry(
                    client.update_distribution,
                    Id=r['Id'], DistributionConfig=config, IfMatch=result['ETag'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidArgument':
                    # CloudFront distributions with pricing plans cannot have their
                    # WAF changed. Skip these resources gracefully.
                    # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/flat-rate-pricing-plan.html
                    if 'pricing plan subscription' in str(e):
                        self.log.warning(
                            "Skipping WAFv2 update for distribution %s: distribution has a "
                            "CloudFront pricing plan subscription which requires a web ACL",
                            r['Id'])
                        continue
                raise


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


class BaseUpdateAction(BaseAction):
    schema = type_schema('set-attributes',
                        attributes={"type": "object"},
                        required=('attributes',))
    schema_alias = False

    def validate(self, config_name, shape):
        attrs = dict(self.data.get('attributes'))
        if attrs.get('CallerReference'):
            raise PolicyValidationError('CallerReference field cannot be updated')

        # Set default values for required fields if they are not present
        attrs["CallerReference"] = ""
        config = self.validation_config
        updatedConfig = {**config, **attrs}

        request = {
            config_name: updatedConfig,
            "Id": "sample_id",
            "IfMatch": "sample_string",
        }
        return shape_validate(request, shape, 'cloudfront')

    def process(self, distributions):
        client = local_session(self.manager.session_factory).client(
            self.manager.get_model().service)
        for d in distributions:
            self.process_distribution(client, d)


@Distribution.action_registry.register('set-attributes')
class DistributionUpdateAction(BaseUpdateAction):
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
    permissions = ("cloudfront:UpdateDistribution",
                   "cloudfront:GetDistributionConfig",)
    shape = 'UpdateDistributionRequest'
    validation_config = {
        'Origins': {
            'Quantity': 0,
            'Items': [{
                'Id': '',
                'DomainName': ''
            }]
        },
        'DefaultCacheBehavior': {
            'TargetOriginId': '',
            'ForwardedValues': {
                'QueryString': True,
                'Cookies': {
                    'Forward': ''
                }
            },
            'TrustedSigners': {
                'Enabled': True,
                'Quantity': 0
            },
            'ViewerProtocolPolicy': '',
            'MinTTL': 0
        },
        'Comment': '',
        'Enabled': False
    }

    def validate(self):
        return super().validate('DistributionConfig', self.shape)

    def process_distribution(self, client, distribution):
        try:
            res = client.get_distribution_config(
                Id=distribution[self.manager.get_model().id])
            default_config = self.validation_config
            config = {**default_config, **res['DistributionConfig']}

            # Recursively merge config to allow piecemeal updates of
            # nested structures
            updatedConfig = merge_dict(config, self.data['attributes'])
            if config == updatedConfig:
                return
            res = client.update_distribution(
                Id=distribution[self.manager.get_model().id],
                IfMatch=res['ETag'],
                DistributionConfig=updatedConfig
            )
        except (client.exceptions.NoSuchDistribution):
            pass
        except Exception as e:
            self.log.warning(
                "Exception trying to update Distribution: %s error: %s",
                distribution['ARN'], e)
            raise e


StreamingDistribution.filter_registry.register('shield-enabled', IsShieldProtected)
StreamingDistribution.action_registry.register('set-shield', SetShieldProtection)


@StreamingDistribution.action_registry.register('set-attributes')
class StreamingDistributionUpdateAction(BaseUpdateAction):
    """Action to update the attributes of a distribution

    :example:

    .. code-block:: yaml

        policies:
        - name: enforce-streaming-distribution-logging
          resource: streaming-distribution
          filters:
            - type: value
              key: "Logging.Enabled"
              value: false
          actions:
            - type: set-attributes
              attributes:
                Logging:
                    Enabled: true
                    Bucket: 'test-enable-logging-c7n.s3.amazonaws.com'
                    Prefix: ''
    """
    permissions = ("cloudfront:UpdateStreamingDistribution",
                   "cloudfront:GetStreamingDistributionConfig",)
    shape = 'UpdateStreamingDistributionRequest'
    validation_config = {
        'S3Origin': {
            'DomainName': 'domain_name',
            'OriginAccessIdentity': 'origin_access_identity'
        },
        'TrustedSigners': {
            'Enabled': False,
            'Quantity': 0
        },
        'Comment': '',
        'Enabled': False
    }

    def validate(self):
        return super().validate('StreamingDistributionConfig', self.shape)

    def process_distribution(self, client, streaming_distribution):
        try:
            res = client.get_streaming_distribution_config(
                Id=streaming_distribution[self.manager.get_model().id])
            default_config = self.validation_config
            config = {**default_config, **res['StreamingDistributionConfig']}
            updatedConfig = {**config, **self.data['attributes']}
            if config == updatedConfig:
                return
            res = client.update_streaming_distribution(
                Id=streaming_distribution[self.manager.get_model().id],
                IfMatch=res['ETag'],
                StreamingDistributionConfig=updatedConfig
            )
        except (client.exceptions.NoSuchStreamingDistribution):
            pass
        except Exception as e:
            self.log.warning(
                "Exception trying to update Streaming Distribution: %s error: %s",
                streaming_distribution['ARN'], e)
            raise e
