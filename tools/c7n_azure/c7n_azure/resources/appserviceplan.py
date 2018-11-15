# Copyright 2018 Capital One Services, LLC
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

from c7n import utils

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.actions import AzureBaseAction
from c7n_azure.filters import AzureOffHour, AzureOnHour
from azure.mgmt.web import models


@resources.register('appserviceplan')
class AppServicePlan(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.web'
        client = 'WebSiteManagementClient'
        enum_spec = ('app_service_plans', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'kind'
        )

    @staticmethod
    def register(registry, _):
        # Additional filters/actions registered for this resource type
        AppServicePlan.filter_registry.register("offhour", AzureOffHour)
        AppServicePlan.filter_registry.register("onhour", AzureOnHour)


resources.subscribe(resources.EVENT_FINAL, AppServicePlan.register)


@AppServicePlan.action_registry.register('resize-plan')
class ResizePlan(AzureBaseAction):
    """Resize App Service Plans

        .. code-block:: yaml

          policies:
            - name: azure-resize-plan
              resource: azure.appserviceplan
              actions:
               - type: resize-plan
                 size: F1 # F1, D1, S1, S2, S3, P1, P2, P3
                 count: 1
    """

    schema = utils.type_schema(
        'resize-plan',
        **{
            'size': {'type': 'string', 'enum': ['F1', 'D1', 'S1', 'S2', 'S3', 'P1', 'P2', 'P3']},
            'count': {'type': 'integer'}
        }
    )

    def process_resource_set(self, plans):
        client = self.manager.get_client()  # type: azure.mgmt.web.WebSiteManagementClient

        for plan in plans:
            model = models.AppServicePlan(location=plan['location'])

            if 'size' in self.data:
                size = self.data.get('size')
                model.sku = models.SkuDescription()
                model.sku.tier = ResizePlan.lookup_tier(size)
                model.sku.capacity = size[1]
                model.sku.name = size
                model.sku.family = size[0]
                model.sku.size = size

            if 'count' in self.data:
                model.target_worker_count = self.data.get('count')

            client.app_service_plans.update(plan['resourceGroup'], plan['name'], model)

    @staticmethod
    def lookup_tier(size):
        tiers = {
            'F': 'Free',
            'S': 'Standard',
            'D': 'Shared',
            'P': 'Premium'
        }
        return tiers.get(size[0])
