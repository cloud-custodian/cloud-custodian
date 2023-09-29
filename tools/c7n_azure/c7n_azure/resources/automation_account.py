from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('automation-account')
class AutomationAccount(ArmResourceManager):
    """Azure Account Automation Resource

    :example:

    This policy will lists the Automation Accounts within an Azure subscription

    .. code-block:: yaml

        policies:
          - name: automation-account
            resource: azure.automation-account
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Network']

        service = 'azure.mgmt.automation'
        client = 'AutomationClient'
        enum_spec = ('automation_account', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Automation/automationAccounts'
