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
                 size: F1
                 count: 1
    """

    schema = utils.type_schema(
        'resize-plan',
        **{
            'size': {'type': 'string', 'enum':
                    ['F1', 'B1', 'B2', 'B3', 'D1', 'S1', 'S2', 'S3', 'P1', 'P2',
                     'P3', 'P1V2', 'P2V2', 'P3v2', 'PC2', 'PC3', 'PC4']},
            'count': {'type': 'integer'}
        }
    )

    def _prepare_processing(self,):
        self.client = self.manager.get_client()  # type: azure.mgmt.web.WebSiteManagementClient

    def _process_resource(self, resource):
        model = models.AppServicePlan(location=resource['location'])

        if 'size' in self.data:
            size = self.data.get('size')
            model.sku = models.SkuDescription()
            model.sku.tier = ResizePlan.get_sku_name(size)
            model.sku.name = size

        if 'count' in self.data:
            model.target_worker_count = self.data.get('count')

        try:
            self.client.app_service_plans.update(resource['resourceGroup'], resource['name'], model)
        except models.DefaultErrorResponseException as e:
            self.log.error("Failed to resize %s.  Inner exception: %s" %
                           (resource['name'], e.inner_exception))

    @staticmethod
    def get_sku_name(tier):
        tier = tier.upper()
        if tier == 'F1':
            return 'FREE'
        elif tier == 'D1':
            return 'SHARED'
        elif tier in ['B1', 'B2', 'B3']:
            return 'BASIC'
        elif tier in ['S1', 'S2', 'S3']:
            return 'STANDARD'
        elif tier in ['P1', 'P2', 'P3']:
            return 'PREMIUM'
        elif tier in ['P1V2', 'P2V2', 'P3V2']:
            return 'PREMIUMV2'
        elif tier in ['PC2', 'PC3', 'PC4']:
            return 'PremiumContainer'
        return None
