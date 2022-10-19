# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_azure.provisioning.deployment_unit import DeploymentUnit
from c7n_azure import constants


class AutoScaleUnit(DeploymentUnit):
    def __init__(self):
        super(AutoScaleUnit, self).__init__(
            'azure.mgmt.monitor.MonitorManagementClient')
        self.type = "AutoScale"

    def _get(self, params):
        # autoscale is enabled only if AppServicePlan is provisioned
        # as a result, it is guaranteed not to have one.
        return None

    def _provision(self, params):
        auto_scale_parameters = {
            "location": params['location'],
            "targetResourceUri": params['service_plan_id'],
            "properties": {
                "enabled": True,
                "profiles": [
                    {
                        "name": "Cloud Custodian auto created scale condition",
                        "capacity": {
                            "minimum": params['min_capacity'],
                            "maximum": params['max_capacity'],
                            "default": params['default_capacity']
                        },
                        "rules": [
                            {
                                "scaleAction": {
                                    "direction": "Increase",
                                    "type": "ChangeCount",
                                    "value": "1",
                                    "cooldown": "PT5M"
                                },
                                "metricTrigger": {
                                    "metricName": "MemoryPercentage",
                                    "metricNamespace": "microsoft.web/serverfarms",
                                    "metricResourceUri": params['service_plan_id'],
                                    "operator": "GreaterThan",
                                    "statistic": "Average",
                                    "threshold": 80,
                                    "timeAggregation": "Average",
                                    "timeGrain": "PT1M",
                                    "timeWindow": "PT10M",
                                    "Dimensions": []
                                }
                            }
                        ]
                    }
                ]
            }
        }

        return self.client.autoscale_settings.create_or_update(params['resource_group_name'],
                                                               constants.FUNCTION_AUTOSCALE_NAME,
                                                               auto_scale_parameters)
