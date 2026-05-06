from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('budget')
class Budget(ArmResourceManager):
    """Budget Resource

    Cost budgets are augmented with a computed ``c7n:percent-used`` field, which is the
    percentage of ``properties.currentSpend.amount`` relative to ``properties.amount``.

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

    Find cost budgets that have used at least 80% of their configured amount:

    .. code-block:: yaml

        policies:
        - name: azure-budget-high-utilization
            resource: azure.budget
            filters:
            - properties.category: Cost
            - type: value
                key: c7n:percent-used
                op: greater-than
                value: 80
    """

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.consumption'
        client = 'ConsumptionManagementClient'
        enum_spec = ('budgets', 'list', None)
        default_report_fields = (
            'id',
            'name',
            'properties.category',
        )
        resource_type = 'Microsoft.Consumption/budgets'

        @classmethod
        def extra_args(cls, resource_manager):
            scope = '/subscriptions/' + resource_manager.get_session().get_subscription_id()
            return {'scope': scope}

    @staticmethod
    def percent_used(resource):
        """Returns what percentage of the budget has already been spent. If the budget is not a Cost
        budget, returns None."""
        props = resource['properties']
        if props['category'] == 'Cost':
            return props['currentSpend']['amount'] / props['amount'] * 100

    def augment(self, resources):
        resources = super().augment(resources)

        for resource in resources:
            percent_used = self.percent_used(resource)
            if percent_used is not None:
                resource['c7n:percent-used'] = percent_used

        return resources
