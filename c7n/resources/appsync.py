# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from c7n.actions import BaseAction, Action
from c7n.filters import ValueFilter, WafV2FilterBase
from c7n.manager import resources
from c7n.query import (
    QueryResourceManager, ChildResourceManager, TypeInfo,
    DescribeSource, ChildDescribeSource)
from c7n.utils import local_session, type_schema, get_retry
from botocore.exceptions import ClientError


@resources.register('graphql-api')
class GraphQLApi(QueryResourceManager):
    """Resource Manager for AppSync GraphQLApi
    """
    class resource_type(TypeInfo):
        service = 'appsync'
        enum_spec = ('list_graphql_apis', 'graphqlApis', {'maxResults': 25})
        id = 'apiId'
        name = 'name'
        config_type = cfn_type = 'AWS::AppSync::GraphQLApi'
        arn_type = 'apis'
        arn = 'arn'
        universal_taggable = True
        permissions_augment = ("appsync:ListTagsForResource",)


@GraphQLApi.filter_registry.register('wafv2-enabled')
class WafV2Enabled(WafV2FilterBase):
    """Filter AppSync GraphQLApi by wafv2 web-acl

    :example:

    .. code-block:: yaml

            policies:
              - name: filter-graphql-api-wafv2
                resource: graphql-api
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: test-waf-v2
              - name: filter-graphql-api-wafv2-regex
                resource: graphql-api
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: .*FMManagedWebACLV2-?FMS-.*
    """

    def get_associated_web_acl(self, resource):
        return self.get_web_acl_by_arn(resource.get('wafWebAclArn'))


@GraphQLApi.filter_registry.register('api-cache')
class ApiCache(ValueFilter):
    """Filter AppSync GraphQLApi based on the api cache attributes

    :example:

    .. code-block:: yaml

       policies:
         - name: filter-graphql-api-cache
           resource: aws.graphql-api
           filters:
            - type: api-cache
              key: 'apiCachingBehavior'
              value: 'FULL_REQUEST_CACHING'
    """
    permissions = ('appsync:GetApiCache',)
    schema = type_schema('api-cache', rinherit=ValueFilter.schema)
    annotation_key = 'c7n:ApiCaches'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('appsync')
        results = []
        for r in resources:
            if self.annotation_key not in r:
                try:
                    api_cache = client.get_api_cache(apiId=r['apiId'])['apiCache']
                except client.exceptions.NotFoundException:
                    continue

                r[self.annotation_key] = api_cache

            if self.match(r[self.annotation_key]):
                results.append(r)

        return results


@GraphQLApi.action_registry.register('set-wafv2')
class SetWafv2(BaseAction):
    """Enable wafv2 protection on AppSync graphqlApi.

    :example:

    .. code-block:: yaml

            policies:
              - name: set-wafv2-for-graphql-api
                resource: graphql-api
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: test-waf-v2
                actions:
                  - type: set-wafv2
                    state: true
                    force: true
                    web-acl: test-waf-v2

              - name: unset-wafv2-for-graphql-api
                resource: graphql-api
                filters:
                  - type: wafv2-enabled
                    state: true
                actions:
                  - type: set-wafv2
                    state: true
                    force: true
                    web-acl: test-waf-v2

            policies:
              - name: set-wafv2-for-graphql-api-regex
                resource: graphql-api
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: .*FMManagedWebACLV2-?FMS-.*
                actions:
                  - type: set-wafv2
                    state: true
                    force: true
                    web-acl: FMManagedWebACLV2-?FMS-TestWebACL
    """
    permissions = ('wafv2:AssociateWebACL',
                   'wafv2:DisassociateWebACL',
                   'wafv2:ListWebACLs')

    schema = type_schema(
        'set-wafv2', **{
            'web-acl': {'type': 'string'},
            'force': {'type': 'boolean'},
            'state': {'type': 'boolean'}})

    retry = staticmethod(get_retry((
        'ThrottlingException',
        'RequestLimitExceeded',
        'Throttled',
        'ThrottledException',
        'Throttling',
        'Client.RequestLimitExceeded')))

    def process(self, resources):
        wafs = self.manager.get_resource_manager('wafv2').resources(augment=False)
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

        client = local_session(self.manager.session_factory).client('wafv2')
        force = self.data.get('force', False)

        arn_key = self.manager.resource_type.arn

        for r in resources:
            if r.get('wafWebAclArn') and not force:
                continue
            if r.get('wafWebAclArn') == target_acl_id:
                continue
            if state:
                self.retry(client.associate_web_acl,
                           WebACLArn=target_acl_id,
                           ResourceArn=r[arn_key])
            else:
                self.retry(client.disassociate_web_acl,
                           ResourceArn=r[arn_key])


@GraphQLApi.action_registry.register('delete')
class Delete(Action):
    """Delete an AppSync GraphQL API.

    :example:

    .. code-block:: yaml

            policies:
              - name: appsync-delete-unlogged-api
                resource: graphql-api
                filters:
                  - type: value
                    key: logConfig
                    value: absent
                actions:
                  - delete

    """
    schema = type_schema('delete')
    permissions = ("appsync:DeleteGraphqlApi",)

    def process(self, apis):
        client = local_session(self.manager.session_factory).client('appsync')
        for api in apis:
            try:
                client.delete_graphql_api(apiId=api['apiId'])
            except ClientError as e:
                if e.response['Error']['Code'] == "ResourceNotFoundException":
                    continue
                raise


def _normalize_tags(resources):
    for r in resources:
        r['Tags'] = [{'Key': k, 'Value': v} for k, v in r.pop('tags', {}).items()]
    return resources


class EventApiDescribe(DescribeSource):

    def augment(self, resources):
        return _normalize_tags(super().augment(resources))


@resources.register('appsync-event-api')
class EventApi(QueryResourceManager):
    """AppSync Event API

    https://docs.aws.amazon.com/appsync/latest/eventapi/event-api-welcome.html

    :example:

    .. code-block:: yaml

        policies:
          - name: appsync-event-api-default-auth-allows-api-key
            resource: aws.appsync-event-api
            filters:
              - type: value
                key: eventConfig.defaultPublishAuthModes[].authType
                op: contains
                value: API_KEY
    """
    class resource_type(TypeInfo):
        service = 'appsync'
        enum_spec = ('list_apis', 'apis', None)
        detail_spec = ('get_api', 'apiId', 'apiId', 'api')
        id = 'apiId'
        name = 'name'
        arn = 'apiArn'
        arn_type = 'apis'
        date = 'created'
        cfn_type = 'AWS::AppSync::Api'
        universal_taggable = object()

    source_mapping = {'describe': EventApiDescribe}


class ChannelNamespaceDescribe(ChildDescribeSource):

    def augment(self, resources):
        # list_channel_namespaces omits auth modes and handler config
        client = local_session(self.manager.session_factory).client('appsync')
        results = []
        for r in super().augment(resources):
            try:
                results.append(self.manager.retry(
                    client.get_channel_namespace,
                    apiId=r['apiId'], name=r['name'])['channelNamespace'])
            except client.exceptions.NotFoundException:
                continue
        return _normalize_tags(results)


@resources.register('appsync-channel-namespace')
class ChannelNamespace(ChildResourceManager):
    """AppSync Event API Channel Namespace

    https://docs.aws.amazon.com/appsync/latest/eventapi/channel-namespaces.html

    :example:

    .. code-block:: yaml

        policies:
          - name: appsync-channel-namespace-tagged
            resource: aws.appsync-channel-namespace
            filters:
              - "tag:Owner": absent
    """
    class resource_type(TypeInfo):
        service = 'appsync'
        parent_spec = ('appsync-event-api', 'apiId', None)
        enum_spec = ('list_channel_namespaces', 'channelNamespaces', None)
        arn = id = 'channelNamespaceArn'
        name = 'name'
        arn_type = 'apis'
        date = 'lastModified'
        cfn_type = 'AWS::AppSync::ChannelNamespace'
        universal_taggable = object()
        permissions_augment = ('appsync:GetChannelNamespace',)

    source_mapping = {'describe-child': ChannelNamespaceDescribe}


@ChannelNamespace.filter_registry.register('auth-modes')
class ChannelNamespaceAuthModes(ValueFilter):
    """Filter channel namespaces on their effective publish or subscribe auth modes.

    A namespace that does not set its own modes inherits the default modes of its
    Event API, so this filter resolves the effective list before matching. ``key``
    selects the operation; the resolved auth types are matched as a list of
    strings, e.g. ``['AWS_IAM', 'API_KEY']``.

    :example:

    .. code-block:: yaml

        policies:
          - name: appsync-channel-namespace-allows-api-key
            resource: aws.appsync-channel-namespace
            filters:
              - or:
                - type: auth-modes
                  key: publish
                  op: contains
                  value: API_KEY
                - type: auth-modes
                  key: subscribe
                  op: contains
                  value: API_KEY
    """
    schema = type_schema(
        'auth-modes', rinherit=ValueFilter.schema,
        required=['key'],
        key={'enum': ['publish', 'subscribe']})
    permissions = ('appsync:ListApis', 'appsync:GetApi')
    annotation_key = 'c7n:AuthModes'

    def process(self, resources, event=None):
        unresolved = [r for r in resources if self.annotation_key not in r]
        if unresolved:
            parent = self.manager.get_parent_manager()
            apis = {
                a['apiId']: a for a in parent.get_resources(
                    list({r['apiId'] for r in unresolved}))}
        for r in unresolved:
            defaults = apis.get(r['apiId'], {}).get('eventConfig', {})
            r[self.annotation_key] = {
                op: [m['authType'] for m in (
                    r.get('%sAuthModes' % op) or
                    defaults.get('default%sAuthModes' % op.title(), []))]
                for op in ('publish', 'subscribe')}
        return [r for r in resources if self.match(r[self.annotation_key])]
