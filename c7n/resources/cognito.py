# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters import WafV2FilterBase
from c7n.filters.core import ListItemFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema


class DescribeIdentityPool(DescribeSource):
    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self.manager, resources)


class DescribeUserPool(DescribeSource):
    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self.manager, resources)


@resources.register('identity-pool')
class CognitoIdentityPool(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cognito-identity'
        enum_spec = ('list_identity_pools', 'IdentityPools', {'MaxResults': 60})
        detail_spec = (
            'describe_identity_pool', 'IdentityPoolId', 'IdentityPoolId', None)
        id = 'IdentityPoolId'
        name = 'IdentityPoolName'
        arn_type = "identitypool"
        config_type = cfn_type = 'AWS::Cognito::IdentityPool'
        universal_taggable = object()
        permissions_augment = ("cognito-identity:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeIdentityPool,
    }


@CognitoIdentityPool.action_registry.register('delete')
class DeleteIdentityPool(BaseAction):
    """Action to delete cognito identity pool

    It is recommended to use a filter to avoid unwanted deletion of pools

    :example:

    .. code-block:: yaml

            policies:
              - name: identity-pool-delete
                resource: identity-pool
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("cognito-identity:DeleteIdentityPool",)

    def process(self, pools):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_pool, pools))

    def process_pool(self, pool):
        client = local_session(
            self.manager.session_factory).client('cognito-identity')
        try:
            client.delete_identity_pool(IdentityPoolId=pool['IdentityPoolId'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting identity pool:\n %s" % e)


@resources.register('user-pool')
class CognitoUserPool(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "cognito-idp"
        enum_spec = ('list_user_pools', 'UserPools', {'MaxResults': 60})
        detail_spec = (
            'describe_user_pool', 'UserPoolId', 'Id', 'UserPool')
        id = 'Id'
        name = 'Name'
        arn = 'Arn'
        arn_type = "userpool"
        config_type = cfn_type = 'AWS::Cognito::UserPool'
        universal_taggable = object()
        permissions_augment = ("cognito-idp:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeUserPool,
    }


@CognitoUserPool.filter_registry.register('wafv2-enabled')
class WafV2Filter(WafV2FilterBase):
    """Filter Cognito UserPool by wafv2 web-acl

    :example:

    .. code-block:: yaml

            policies:
              - name: filter-userpool-wafv2
                resource: user-pool
                filters:
                  - type: wafv2-enabled
                    state: false
              - name: filter-userpool-wafv2-regex
                resource: user-pool
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: .*FMManagedWebACLV2-?FMS-.*
    """

    # cognito user pools don't hold a reference to the associated web acl
    # so we have to look them up via the associations on the web acl directly
    def get_associated_web_acl(self, resource):
        return self.get_web_acl_from_associations(
            'COGNITO_USER_POOL',
            resource['Arn']
        )


@CognitoUserPool.filter_registry.register('app-client')
class UserPoolAppClientFilter(ListItemFilter):
    """Filter Cognito user pools by the configuration of their app clients

    Attributes are matched against the output of DescribeUserPoolClient.
    The client secret is never retained; ``c7n:HasClientSecret`` indicates
    whether the app client has one.

    :example:

    Find user pools with app clients that allow the OAuth implicit grant:

    .. code-block:: yaml

            policies:
              - name: user-pool-client-implicit-grant
                resource: aws.user-pool
                filters:
                  - type: app-client
                    attrs:
                      - type: value
                        key: AllowedOAuthFlows
                        value: implicit
                        op: contains

    Find user pools with app clients that allow password auth without a
    client secret:

    .. code-block:: yaml

            policies:
              - name: user-pool-client-password-auth-without-secret
                resource: aws.user-pool
                filters:
                  - type: app-client
                    attrs:
                      - type: value
                        key: ExplicitAuthFlows
                        value: ALLOW_USER_PASSWORD_AUTH
                        op: contains
                      - type: value
                        key: '"c7n:HasClientSecret"'
                        value: false
    """
    schema = type_schema(
        'app-client',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )
    permissions = (
        'cognito-idp:ListUserPoolClients',
        'cognito-idp:DescribeUserPoolClient',
    )
    annotate_items = True
    item_annotation_key = 'c7n:MatchedAppClients'
    cache_key = 'c7n:AppClients'

    def get_item_values(self, resource):
        if self.cache_key in resource:
            return resource[self.cache_key]
        client = local_session(self.manager.session_factory).client('cognito-idp')
        summaries = client.get_paginator('list_user_pool_clients').paginate(
            UserPoolId=resource['Id'], MaxResults=60
        ).build_full_result().get('UserPoolClients', [])
        app_clients = []
        for summary in summaries:
            try:
                app_client = client.describe_user_pool_client(
                    UserPoolId=resource['Id'], ClientId=summary['ClientId']
                )['UserPoolClient']
            except client.exceptions.ResourceNotFoundException:
                continue
            app_client['c7n:HasClientSecret'] = bool(
                app_client.pop('ClientSecret', None))
            app_clients.append(app_client)
        resource[self.cache_key] = app_clients
        return app_clients


@CognitoUserPool.filter_registry.register('identity-provider')
class UserPoolIdentityProviderFilter(ListItemFilter):
    """Filter Cognito user pools by their federated identity providers

    Attributes are matched against the output of DescribeIdentityProvider.
    Credential values in ``ProviderDetails`` (``client_secret``,
    ``private_key``) are never retained.

    :example:

    Find user pools federated with social identity providers:

    .. code-block:: yaml

            policies:
              - name: user-pool-social-identity-providers
                resource: aws.user-pool
                filters:
                  - type: identity-provider
                    attrs:
                      - type: value
                        key: ProviderType
                        op: in
                        value:
                          - Google
                          - Facebook
                          - LoginWithAmazon
                          - SignInWithApple
    """
    schema = type_schema(
        'identity-provider',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )
    permissions = (
        'cognito-idp:ListIdentityProviders',
        'cognito-idp:DescribeIdentityProvider',
    )
    annotate_items = True
    item_annotation_key = 'c7n:MatchedIdentityProviders'
    cache_key = 'c7n:IdentityProviders'
    secret_provider_details = ('client_secret', 'private_key')

    def get_item_values(self, resource):
        if self.cache_key in resource:
            return resource[self.cache_key]
        client = local_session(self.manager.session_factory).client('cognito-idp')
        summaries = client.get_paginator('list_identity_providers').paginate(
            UserPoolId=resource['Id'], MaxResults=60
        ).build_full_result().get('Providers', [])
        providers = []
        for summary in summaries:
            try:
                provider = client.describe_identity_provider(
                    UserPoolId=resource['Id'], ProviderName=summary['ProviderName']
                )['IdentityProvider']
            except client.exceptions.ResourceNotFoundException:
                continue
            details = provider.get('ProviderDetails', {})
            for key in self.secret_provider_details:
                details.pop(key, None)
            providers.append(provider)
        resource[self.cache_key] = providers
        return providers


@CognitoUserPool.filter_registry.register('log-delivery')
class UserPoolLogDeliveryFilter(ListItemFilter):
    """Filter Cognito user pools by their log delivery configuration

    Attributes are matched against each entry of ``LogConfigurations``
    from GetLogDeliveryConfiguration.

    :example:

    Find user pools that do not export user auth events to CloudWatch Logs:

    .. code-block:: yaml

            policies:
              - name: user-pool-auth-events-not-in-cloudwatch
                resource: aws.user-pool
                filters:
                  - type: log-delivery
                    count: 0
                    attrs:
                      - EventSource: userAuthEvents
                      - type: value
                        key: CloudWatchLogsConfiguration.LogGroupArn
                        value: present
    """
    schema = type_schema(
        'log-delivery',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )
    permissions = ('cognito-idp:GetLogDeliveryConfiguration',)
    annotate_items = True
    item_annotation_key = 'c7n:MatchedLogConfigurations'
    cache_key = 'c7n:LogConfigurations'

    def get_item_values(self, resource):
        if self.cache_key not in resource:
            client = local_session(self.manager.session_factory).client('cognito-idp')
            response = client.get_log_delivery_configuration(UserPoolId=resource['Id'])
            resource[self.cache_key] = response.get(
                'LogDeliveryConfiguration', {}).get('LogConfigurations', [])
        return resource[self.cache_key]


@CognitoUserPool.action_registry.register('delete')
class DeleteUserPool(BaseAction):
    """Action to delete cognito user pool

    It is recommended to use a filter to avoid unwanted deletion of pools

    :example:

    .. code-block:: yaml

            policies:
              - name: user-pool-delete
                resource: user-pool
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("cognito-idp:DeleteUserPool",)

    def process(self, pools):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_pool, pools))

    def process_pool(self, pool):
        client = local_session(
            self.manager.session_factory).client('cognito-idp')
        try:
            client.delete_user_pool(UserPoolId=pool['Id'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting user pool:\n %s" % e)
