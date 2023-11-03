from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.filters import ValueFilter
from c7n.utils import type_schema
from c7n.filters.core import OPERATORS


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


@AutomationAccount.filter_registry.register('variable')
class VariableValueFilter(ValueFilter):
    """Azure Variable Value Filter

    :example:

    Filter is used for searching extended list of variables in
    automation account resource

    .. code-block:: yaml

        policies:
          - name: automation-account
            resource: azure.automation-account
            filters:
              - type: variable
                key: is_encrypted
                op: eq
                value: False
    """
    schema = type_schema('variable', rinherit=ValueFilter.schema)

    def _op(self, a, b):
        op = OPERATORS[self.data.get('op')]
        return op(a, b)

    def process(self, resources, event=None):
        self.key = self.data.get('key')
        self.value = self.data.get('value')
        client = self.manager.get_client('azure.mgmt.automation.AutomationClient')
        accepted_resources = []
        for resource in resources:
            variables = list(client.variable.list_by_automation_account(
                automation_account_name=resource['name'],
                resource_group_name=resource['resourceGroup']))
            for variable in variables:
                path_key = getattr(variable, self.key)
                if path_key is not None and self._op(path_key, self.value):
                    accepted_resources.append(resource)
                    break

        return accepted_resources
