# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n import query
from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry
from c7n.manager import resources, ResourceManager
from c7n.utils import local_session, get_retry, type_schema


class DescribeQuicksight(query.DescribeSource):

    def resources(self, query):
        required = {
            "Namespace": "default",
            "AwsAccountId": self.manager.config.account_id
        }
        try:
            required_resources = super().resources(required)
        except ClientError as e:
            if is_quicksight_account_missing(e):
                return []
            raise
        return required_resources


@resources.register("quicksight-user")
class QuicksightUser(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "quicksight"
        enum_spec = ('list_users', 'UserList', None)
        arn_type = "user"
        arn = "Arn"
        id = "UserName"
        name = "UserName"

    source_mapping = {
        "describe": DescribeQuicksight,
    }


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
class QuicksightGroup(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "quicksight"
        enum_spec = ('list_groups', 'GroupList', None)
        arn_type = "group"
        arn = "Arn"
        id = "GroupName"
        name = "GroupName"

    source_mapping = {
        "describe": DescribeQuicksight,
    }


@resources.register("quicksight-account")
class QuicksightAccount(ResourceManager):
    # note this is not using a regular resource manager or type info
    # its a pseudo resource, like an aws account

    filter_registry = FilterRegistry('quicksight-account.filters')
    action_registry = ActionRegistry('quicksight-account.actions')
    retry = staticmethod(get_retry((
        'ThrottlingException', 'InternalFailureException',
        'ResourceUnavailableException')))

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
            else:
                raise
        return required_resources

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('quicksight')
        for r in resources:
            tags = self.manager.retry(client.list_tags_for_resource,
                                ResourceArn=r['Arn'],
                                ignore_err_codes=("ResourceNotFoundException",))['Tags']
            r['Tags'] = tags
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

    source_mapping = {
        "describe": DescribeQuicksightWithAccountId,
    }


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
