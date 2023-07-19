# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from c7n.actions import BaseAction, Action
from c7n.filters import Filter, ValueFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
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
        cfn_type = 'AWS::AppSync::GraphQLApi'
        arn_type = 'apis'
        arn = 'arn'
        universal_taggable = True


@GraphQLApi.filter_registry.register('wafv2-enabled')
class WafV2Enabled(Filter):
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

    schema = type_schema(
        'wafv2-enabled', **{
            'web-acl': {'type': 'string'},
            'state': {'type': 'boolean'}})

    permissions = ('wafv2:ListWebACLs',)

    def process(self, resources, event=None):
        wafs = self.manager.get_resource_manager('wafv2').resources(augment=False)
        waf_name_id_map = {w['Name']: w['ARN'] for w in wafs}

        target_acl = self.data.get('web-acl', '')
        state = self.data.get('state', False)
        target_acl_ids = [v for k, v in waf_name_id_map.items() if
                          re.match(target_acl, k)]

        results = []
        for r in resources:
            r_web_acl_id = r.get('wafWebAclArn')
            if state:
                if not target_acl and r_web_acl_id:
                    results.append(r)
                elif target_acl and r_web_acl_id in target_acl_ids:
                    results.append(r)
            else:
                if not target_acl and not r_web_acl_id:
                    results.append(r)
                elif target_acl and r_web_acl_id not in target_acl_ids:
                    results.append(r)
        return results


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
