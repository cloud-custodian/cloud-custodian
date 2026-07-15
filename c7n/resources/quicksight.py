# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n import query
from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, ValueFilter, ANNOTATION_KEY
from c7n.manager import resources, ResourceManager
from c7n.tags import Tag, RemoveTag, TagDelayedAction, TagActionFilter
from c7n.utils import local_session, get_retry, set_annotation, type_schema


QUICKSIGHT_RETRY = get_retry((
    'ThrottlingException',
    'InternalFailureException',
    'ResourceUnavailableException'))


class DescribeNamespacedQuicksight(query.DescribeSource):

    def get_resources(self, ids, cache=True):
        m = self.manager.get_model()
        return [r for r in self.resources(None) if r[m.id] in ids]

    def resources(self, query):
        required = {
            "Namespace": self.manager.namespace,
            "AwsAccountId": self.manager.account_id
        }
        try:
            required_resources = super().resources(required)
        except ClientError as e:
            if is_quicksight_account_missing(e):
                return []
            raise
        return required_resources


class DescribeQuicksightUser(DescribeNamespacedQuicksight):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('quicksight')
        for r in resources:
            result = self.manager.retry(client.list_tags_for_resource,
                                ResourceArn=r['Arn'],
                                ignore_err_codes=("ResourceNotFoundException",))
            r['Tags'] = result.get('Tags', []) if result else []
        return resources


class QuicksightNamespacedResourceManager(query.QueryResourceManager):

    retry = staticmethod(QUICKSIGHT_RETRY)

    source_mapping = {
        "describe": DescribeNamespacedQuicksight,
    }

    @property
    def account_id(self):
        return self.config.account_id

    @property
    def namespace(self):
        for q in self.data.get('query', []):
            if 'Namespace' in q:
                return q['Namespace']
        return "default"


@resources.register("quicksight-user")
class QuicksightUser(QuicksightNamespacedResourceManager):
    class resource_type(query.TypeInfo):
        service = "quicksight"
        enum_spec = ('list_users', 'UserList', None)
        arn_type = "user"
        arn = "Arn"
        id = "UserName"
        name = "UserName"
        permissions_augment = ("quicksight:ListTagsForResource",)

    source_mapping = {
        "describe": DescribeQuicksightUser,
    }


@QuicksightUser.filter_registry.register('permissions')
class QuicksightUserPermissionsFilter(ValueFilter):

    annotation_key = 'c7n:CustomPermissions'
    permissions = ('quicksight:DescribeCustomPermissions',)
    schema = type_schema('permissions', rinherit=ValueFilter.schema)
    schema_alias = False

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('quicksight')
        account_id = self.manager.account_id
        for r in resources:
            if self.annotation_key in r:
                continue
            name = r.get('CustomPermissionsName')
            if not name:
                r[self.annotation_key] = {}
                continue
            result = self.manager.retry(
                client.describe_custom_permissions,
                CustomPermissionsName=name,
                AwsAccountId=account_id,
                ignore_err_codes=('ResourceNotFoundException',))
            r[self.annotation_key] = result['CustomPermissions'] if result else {}
        return super().process(resources, event)

    def __call__(self, r):
        matched = self.match(r[self.annotation_key])
        if matched and self.annotate:
            set_annotation(r, ANNOTATION_KEY, self.k)
        return matched


class TagQuicksight(Tag):
    """Add tag(s) to a quicksight resource.

    :example:

    .. code-block:: yaml

        policies:
          - name: quicksight-user-tag
            resource: aws.quicksight-user
            filters:
              - "tag:Owner": absent
            actions:
              - type: tag
                key: Owner
                value: platform-team
    """

    permissions = ('quicksight:TagResource',)

    def process_resource_set(self, client, resource_set, new_tags):
        for r in resource_set:
            self.manager.retry(
                client.tag_resource,
                ResourceArn=r['Arn'],
                Tags=new_tags,
                ignore_err_codes=('ResourceNotFoundException',))


class RemoveTagQuicksight(RemoveTag):
    """Remove tag(s) from a quicksight resource.

    :example:

    .. code-block:: yaml

        policies:
          - name: quicksight-user-remove-tag
            resource: aws.quicksight-user
            filters:
              - "tag:Owner": present
            actions:
              - type: remove-tag
                tags: ["Owner"]
    """

    permissions = ('quicksight:UntagResource',)

    def process_resource_set(self, client, resource_set, tag_keys):
        for r in resource_set:
            self.manager.retry(
                client.untag_resource,
                ResourceArn=r['Arn'],
                TagKeys=tag_keys,
                ignore_err_codes=('ResourceNotFoundException',))


@QuicksightUser.action_registry.register('delete')
class DeleteUserAction(BaseAction):
    schema = type_schema('delete',)
    permissions = ('quicksight:DeleteUser',)

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        client = session.client(self.manager.resource_type.service)
        account_id = self.manager.config.account_id
        for r in resources:
            self.manager.retry(
                client.delete_user,
                AwsAccountId=account_id,
                Namespace='default',
                UserName=r['UserName'],
                ignore_err_codes=('ResourceNotFoundException',)
            )


@resources.register("quicksight-group")
class QuicksightGroup(QuicksightNamespacedResourceManager):
    class resource_type(query.TypeInfo):
        service = "quicksight"
        enum_spec = ('list_groups', 'GroupList', None)
        arn_type = "group"
        arn = "Arn"
        id = "GroupName"
        name = "GroupName"


@resources.register("quicksight-account")
class QuicksightAccount(ResourceManager):
    # note this is not using a regular resource manager or type info
    # its a pseudo resource, like an aws account

    filter_registry = FilterRegistry('quicksight-account.filters')
    action_registry = ActionRegistry('quicksight-account.actions')
    retry = staticmethod(QUICKSIGHT_RETRY)

    class resource_type(query.TypeInfo):
        service = 'quicksight'
        name = id = 'account_id'
        dimension = None
        arn = False
        global_resource = True

    @classmethod
    def get_permissions(cls):
        # this resource is not query manager based as its a pseudo
        # resource. in that it always exists, it represents the
        # service's account settings.
        return ('quicksight:DescribeAccountSettings',)

    @classmethod
    def has_arn(self):
        return False

    def get_model(self):
        return self.resource_type

    def _get_account(self):
        client = local_session(self.session_factory).client('quicksight')
        try:
            account = self.retry(client.describe_account_settings,
                AwsAccountId=self.config.account_id
            )["AccountSettings"]
        except Exception as e:
            if is_quicksight_account_missing(e):
                return []
            raise

        account.pop('ResponseMetadata', None)
        account['account_id'] = 'quicksight-settings'
        return [account]

    def resources(self):
        return self.filter_resources(self._get_account())

    def get_resources(self, resource_ids):
        return self._get_account()


@QuicksightAccount.filter_registry.register('subscription')
class QuicksightAccountSubscription(ValueFilter):
    """Filter quicksight account by its subscription details.

    Calls describe_account_subscription and annotates the resource
    with the returned AccountInfo under the ``c7n:AccountSubscription`` key.

    :example:

    .. code-block:: yaml

        policies:
          - name: quicksight-enterprise-subscription-active
            resource: aws.quicksight-account
            filters:
              - type: subscription
                key: Edition
                value: ENTERPRISE
              - type: subscription
                key: AccountSubscriptionStatus
                value: ACCOUNT_CREATED
    """

    schema = type_schema('subscription', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('quicksight:DescribeAccountSubscription',)
    annotation_key = 'c7n:AccountSubscription'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('quicksight')
        for r in resources:
            if self.annotation_key in r:
                continue
            info = self.manager.retry(
                client.describe_account_subscription,
                AwsAccountId=self.manager.config.account_id
            )['AccountInfo']
            r[self.annotation_key] = info
        return super().process(resources, event)

    def __call__(self, r):
        return super().__call__(r[self.annotation_key])


class DescribeQuicksightWithAccountId(query.DescribeSource):

    def resources(self, query):
        required = {
            "AwsAccountId": self.manager.config.account_id
        }
        try:
            required_resources = super().resources(required)
        except ClientError as e:
            if is_quicksight_account_missing(e):
                return []
            raise
        return required_resources

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('quicksight')
        for r in resources:
            result = self.manager.retry(client.list_tags_for_resource,
                                ResourceArn=r['Arn'],
                                ignore_err_codes=("ResourceNotFoundException",))
            r['Tags'] = result.get('Tags', []) if result else []
        return resources


@resources.register("quicksight-dashboard")
class QuicksightDashboard(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "quicksight"
        enum_spec = ('list_dashboards', 'DashboardSummaryList', None)
        arn_type = "dashboard"
        arn = "Arn"
        id = "DashboardId"
        name = "Name"
        permissions_augment = ("quicksight:ListTagsForResource",)

    retry = staticmethod(QUICKSIGHT_RETRY)

    source_mapping = {
        "describe": DescribeQuicksightWithAccountId,
    }


@resources.register("quicksight-datasource")
class QuicksightDataSource(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "quicksight"
        enum_spec = ('list_data_sources', 'DataSources', None)
        arn_type = "datasource"
        arn = "Arn"
        id = "DataSourceId"
        name = "Name"
        permissions_augment = ("quicksight:ListTagsForResource",)

    retry = staticmethod(QUICKSIGHT_RETRY)

    source_mapping = {
        "describe": DescribeQuicksightWithAccountId,
    }


for klass in (QuicksightUser, QuicksightDashboard, QuicksightDataSource):
    klass.action_registry.register('tag', TagQuicksight)
    klass.action_registry.register('remove-tag', RemoveTagQuicksight)
    klass.action_registry.register('mark-for-op', TagDelayedAction)
    klass.filter_registry.register('marked-for-op', TagActionFilter)


def is_quicksight_account_missing(e):
    """
    Helper to ccheck if QuickSight account is missing or inaccessible.
    This function checks if the error is due to a missing QuickSight account,
    the standard edition being used, or the policy being run from a non-identity
    region. It returns True if any of these conditions are met, allowing us to
    gracefully handle the situation by returning an empty resource list.
    Unfortunately some of these are lumped under AccessDenied, and we would like
    normal AccessDenied Exceptions caused by lack of IAM permissions to still be
    raised, so we check the error code and message.
    """
    error_code = e.response['Error']['Code']
    error_message = e.response['Error'].get('Message', '')

    if error_code == 'ResourceNotFoundException' or (
        error_code == 'AccessDeniedException' and (
            "disabled for STANDARD Edition" in error_message or
            "Operation is being called from endpoint" in error_message
        )) or error_code == 'UnsupportedUserEditionException':
        return True
    return False
