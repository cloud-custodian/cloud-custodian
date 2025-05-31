from azure.mgmt.consumption import ConsumptionManagementClient
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager
from c7n.utils import type_schema

@resources.register('budget')
class AzureBudget(QueryResourceManager):
    """Azure Budget Resource for Subscription"""

    class resource_type:
        service = 'azure.mgmt.consumption'
        client = 'ConsumptionManagementClient'
        enum_spec = ('budgets', 'list', None)

    def resources(self):
        session = self.get_session()
        client = ConsumptionManagementClient(session.get_credentials(), session.subscription_id)
        
        return [
            {
                'name': budget.name,
                'amount': budget.amount,
                'time_grain': budget.time_grain.value,
                'category': budget.category.value,
                'current_spend': budget.current_spend.amount,
                'currency': budget.current_spend.unit
            }
            for budget in client.budgets.list(session.subscription_id)
        ]
