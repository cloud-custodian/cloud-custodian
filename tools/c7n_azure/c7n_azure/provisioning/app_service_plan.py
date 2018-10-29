from azure.mgmt.web.models import AppServicePlan, SkuDescription
from c7n_azure.provisioning.deployment_unit import DeploymentUnit
from c7n_azure.provisioning.resource_group import ResourceGroupUnit


class AppServicePlanUnit(DeploymentUnit):

    def __init__(self):
        super(AppServicePlanUnit, self).__init__(
            'azure.mgmt.web.WebSiteManagementClient')
        self.type = "Application Service Plan"

    def _get(self, params):
        return self.client.app_service_plans.get(params['resource_group_name'],
                                                 params['name'])

    def _provision(self, params):
        rg_unit = ResourceGroupUnit()
        rg_unit.provision_if_not_exists({'name': params['resource_group_name'],
                                         'location': params['location']})

        plan = AppServicePlan(
            app_service_plan_name=params['name'],
            location=params['location'],
            sku=SkuDescription(
                name=params['sku_name'],
                capacity=1,
                tier=params['sku_tier']),
            kind='linux',
            target_worker_size_id=0,
            reserved=True)

        return self.client.app_service_plans.create_or_update(params['resource_group_name'],
                                                              params['name'],
                                                              plan).result()
