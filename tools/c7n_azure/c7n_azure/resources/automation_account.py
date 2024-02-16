from c7n.filters import ListItemFilter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register("automation-account")
class AutomationAccount(ArmResourceManager):
    """Azure Account Automation Resource

    :example:

    This policy will list the Automation Accounts within an Azure subscription

    .. code-block:: yaml

        policies:
          - name: automation-account
            resource: azure.automation-account
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ["Integration"]

        service = "azure.mgmt.automation"
        client = "AutomationClient"
        enum_spec = ("automation_account", "list", None)
        default_report_fields = (
            "name",
            "location",
            "resourceGroup"
        )
        resource_type = "Microsoft.Automation/automationAccounts"


@AutomationAccount.filter_registry.register("variable")
class VariableValueFilter(ListItemFilter):
    """Azure Variable Value Filter

    :example:

    Finds automation accounts that have not encrypted variables

    .. code-block:: yaml

        policies:
          - name: automation-account
            resource: azure.automation-account
            filters:
              - type: variable
                attrs:
                  - type: value
                    key: properties.isEncrypted
                    value: false
    """
    schema = type_schema(
        "variable",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
    )
    annotate_items = True
    item_annotation_key = "c7n:Variables"

    def get_item_values(self, resource):
        client = self.manager.get_client()
        variables = client.variable.list_by_automation_account(
            automation_account_name=resource["name"],
            resource_group_name=resource["resourceGroup"]
        )
        return [v.serialize(True) for v in variables]
