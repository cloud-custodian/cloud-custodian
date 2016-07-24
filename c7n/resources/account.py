
from c7n.actions import BaseAction, ActionRegistry
from c7n.filters import Filter, FilterRegistry
from c7n.manager import ResourceManager
from c7n.utils import local_session


class Account(ResourceManager):


    filter_registry = FilterRegistry('aws.account.actions')
    action_registry = ActionRegistry('aws.account.filters')

    def resources(self):
        client = local_session(self.manager.session_factory).client('iam')
        return {}


class CloudTrailEnabled(Filter):
    """Is cloud trail enabled for this account

    TODO: allow for checking kms key
    """

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudtrail')
        trails = client.describe_trails()['trailList']
        if not trails:
            return resources
        

class ConfigEnabled(Filter):
    """ Is cloud trail enabled for this account
    """

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('config')
        channels = client.describe_delivery_channels()[
            'DeliveryChannels']
        recorders = client.describe_configuration_recorders()[
            'ConfigurationRecorders']
        if channels and recorders:
            return []
        return resources

        
@Account.filter_registry.register('root-access-keys')
class RootAccessKeys(Filter):

    def processs(self, resources):
        client = local_session(self.manager.session_factory).client('iam')
        summary = client.get_account_summary()['SummaryMap']
        if summary['AccountAccessKeysPresent']:
            return resources
        return []

    
@Account.filter_registry.register('root-mfa-enabled')
class RootMFAEnabled(Filter):

    def processs(self, resources):
        client = local_session(self.manager.session_factory).client('iam')
        summary = client.get_account_summary()['SummaryMap']
        if summary['AccountMFAEnabled']:
            return resources
        return []


class AccountPasswordPolicy(Filter):
    """Account password policy
    """

    
class EnableCloudTrail(BaseAction):
    pass


class EnableConfig(BaseAction):
    pass


# ec2 limits
