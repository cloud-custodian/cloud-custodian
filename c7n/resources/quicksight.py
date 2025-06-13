# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n import query
from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import resources, ResourceManager
from c7n.utils import local_session, get_retry


class DescribeQuicksight(query.DescribeSource):

    def resources(self, query):
        required = {
            "Namespace": "default",
            "AwsAccountId": self.manager.config.account_id
        }
        return super().resources(required)


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
        except ClientError as e:
            # Return no resources if no quicksight account has been created, the standard edition is
            # being used, or if the policy is being run from a non-identity region. Otherwise, raise
            # the exception. It's a bit brittle to depend on error messages, but unfortunately
            # these all are lumped under AccessDenied, and we would like normal AccessDenied
            # Exceptions caused by lack of IAM permissions to still be raised.
            error_code = e.response['Error']['Code']
            error_message = e.response['Error'].get('Message', '')

            if error_code == 'ResourceNotFoundException' or (
                error_code == 'AccessDeniedException' and (
                    "disabled for STANDARD Edition" in error_message or
                    "Operation is being called from endpoint" in error_message
                )
            ):
                return []
            raise

        account.pop('ResponseMetadata', None)
        account['account_id'] = 'quicksight-settings'
        return [account]

    def resources(self):
        return self.filter_resources(self._get_account())

    def get_resources(self, resource_ids):
        return self._get_account()
