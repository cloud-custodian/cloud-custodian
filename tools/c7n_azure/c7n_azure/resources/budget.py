from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('budget')
class Budget(ArmResourceManager):
    """Budget Resource

    :example:

    Find budgets with amount > $1000:

    .. code-block:: yaml

        policies:
        - name: azure-budget-list
            resource: azure.budget
            filters:
            - properties.category: Cost
            - type: value
                key: properties.amount
                op: greater-than
                value: 1000
    """

    # TODO: I don't actually know if ArmResourceManager is the right base class here
    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.consumption'
        client = 'ConsumptionManagementClient'
        enum_spec = ('budgets', 'list', None)
        default_report_fields = (
            'id',
            'name',
            'properties.category',
        )
        resource_type = 'Microsoft.CostManagement/budgets'
        # TODO: There may be other attributes to utilize here. Docs are sparse.

        @classmethod
        def extra_args(cls, resource_manager):
            # TODO: This is somewhat inflexible, but see cost_management_export module for precedent
            # Should we accept this as a parameter in the policy definition?
            scope = '/subscriptions/' + resource_manager.get_session().get_subscription_id()
            return {'scope': scope}

    def percent_used(self, resource):
        props = resource['properties']
        return props['currentSpend']['amount'] / props['amount'] * 100

    def augment(self, resources):
        resources = super().augment(resources)

        for resource in resources:
            props = resource['properties']
            if props['category'] == 'Cost':
                # TODO: do we prefix fields we envision using in filters with 'c7n:'?
                resource['c7n:percent-used'] = self.percent_used(resource)

        return resources
