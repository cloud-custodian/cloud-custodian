from c7n_azure.provisioning.deployment_unit import DeploymentUnit
from c7n_azure.provisioning.resource_group import ResourceGroupUnit

class AppInsightsUnit(DeploymentUnit):

    def __init__(self):
        super().__init__()
        self.client = self.session.client('azure.mgmt.applicationinsights.ApplicationInsightsManagementClient')
        self.type = "Application Insights"

    def _get(self, params):
        try:
            return self.client.components.get(params['resource_group_name'], params['name'])
        except:
            return None

    def _provision(self, params):
        rg_unit = ResourceGroupUnit()
        rg_unit.provision_if_not_exists({'name': params['resource_group_name'],
                                         'location': params['location']})

        ai_params = {
            'location': params['location'],
            'application_type': 'web', #params['webapp_name'],
            'request_source': 'IbizaWebAppExtensionCreate',
            'kind': 'web'
        }
        return self.client.components.create_or_update(params['resource_group_name'],
                                                       params['name'],
                                                       ai_params)
