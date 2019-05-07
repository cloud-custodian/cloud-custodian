
from c7n_azure.utils import StringUtils
from c7n_azure.provisioning.resource_group import ResourceGroupUnit
from c7n_azure.provisioning.deployment_unit import DeploymentUnit
from msrestazure.azure_exceptions import CloudError

class AutoScaleUnit(DeploymentUnit):
    def __init__(self):
        super(AutoScaleUnit, self).__init__(
            'azure.mgmt.monitor.MonitorManagementClient')
        self.type = "AutoScale"
        self.target_resource_uri = ""
        self.service_plan_sku = ""

    def _get_autoscale_settings(self):
        return self.client.autoscale_settings

    def _get(self, params):
            return None

    def set_service_plan_id(self, app_service_plan_id):
        self.target_resource_uri = app_service_plan_id

    def set_sku_tier(self, app_service_plan_sku):
        self.service_plan_sku = app_service_plan_sku

    def _check_app_service_plan_sku(self):
        is_dynamic = StringUtils.equal(self.service_plan_sku, 'dynamic')
        return is_dynamic

    def _provision(self, params):
        rg_unit = ResourceGroupUnit()
        rg_unit.provision_if_not_exists({'name': params['resource_group_name'],
                                         'location': params['location']})

        auto_scale_parameters = {
            "location": params['location'],
            "targetResourceUri": self.target_resource_uri,
            "properties": {
                "enabled": params['auto_scale']['enable_auto_scale'],
                "profiles": [
                    {
                        "name": "Auto created scale condition",
                        "capacity": {
                            "minimum": params['auto_scale']['min_capacity'],
                            "maximum": params['auto_scale']['max_capacity'],
                            "default": params['auto_scale']['default_capacity']
                        },
                        "rules": []
                    }
                ]
            }
        }

        # call API if autoscale is enabled and app service plan is dynamic
        is_enabled = params['auto_scale']['enable_auto_scale']
        is_dynamic = self._check_app_service_plan_sku()
        if is_dynamic and is_enabled:
            self._get_autoscale_settings().create_or_update(params['resource_group_name'], "autoscale", auto_scale_parameters)
