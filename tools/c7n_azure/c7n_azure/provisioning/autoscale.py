# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
