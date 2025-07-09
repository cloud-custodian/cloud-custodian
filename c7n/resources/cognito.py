# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters import WafV2FilterBase
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
