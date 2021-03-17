# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.web import models
from c7n.lookup import Lookup
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('appserviceplan')
class AppServicePlan(ArmResourceManager):
    """Application Service Plan

    :example:

    Find all App Service Plans that are of the Basic sku tier.

    .. code-block:: yaml

        policies:
          - name: basic-tier-plans
            resource: azure.appserviceplan
            filters:
              - type: value
                key: sku.tier
                op: eq
                value: Basic

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute', 'Web']

        service = 'azure.mgmt.web'
        client = 'WebSiteManagementClient'
        enum_spec = ('app_service_plans', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'kind',
            'sku.[name, tier, capacity]'
        )
        resource_type = 'Microsoft.Web/serverfarms'


@AppServicePlan.action_registry.register('resize-plan')
class ResizePlan(AzureBaseAction):
    """Resize App Service Plans

    :example:

    Resize App Service Plan to B1 plan with 2 instance.

    .. code-block:: yaml

        policies:
        - name: azure-resize-plan
          resource: azure.appserviceplan
          actions:
           - type: resize-plan
             size: B1
             count: 2


    :example:

    Resize app service plans with on/off hours and resource tagging

    .. code-block:: yaml

        policies:
          - name: on-hours
            resource: azure.appserviceplan
            filters:
              - type: onhour
                default_tz: pt
                onhour: 8
                tag: onoffhour_schedule
            actions:
              - type: resize-plan
                size:
                    type: resource
                    key: tags.on_hour_sku
                    default-value: P1

          - name: off-hours
            resource: azure.appserviceplan
            filters:
              - type: offhour
                default_tz: pt
                offhour: 19
                tag: onoffhour_schedule
            actions:
              - type: tag
                tag: on_hour_sku
                value:
                    type: resource
                    key: sku.name
              - type: resize-plan
                size: S1

    """

    schema = {
        'type': 'object',
        'anyOf': [
            {'required': ['size']},
            {'required': ['count']}
        ],
        'properties': {
            'type': {'enum': ['resize-plan']},
            'size': Lookup.lookup_type({'type': 'string',
                                        'enum': ['F1', 'B1', 'B2', 'B3', 'D1',
                                                 'S1', 'S2', 'S3', 'P1', 'P2',
                                                 'P3', 'P1V2', 'P2V2', 'P3v2',
                                                 'PC2', 'PC3', 'PC4']
                                        }),
            'count': Lookup.lookup_type({'type': 'integer'})
        },
        'additionalProperties': False
    }
    schema_alias = True

    def _prepare_processing(self):
        self.client = self.manager.get_client()  # type azure.mgmt.web.WebSiteManagementClient

    def _process_resource(self, resource):
        model = models.AppServicePlan(location=resource['location'])

        if resource['kind'] == 'functionapp':
            self.log.info("Skipping %s, because this App Service Plan "
                          "is for Consumption Azure Functions." % resource['name'])
            return

        if resource['kind'] == 'linux':
            model.reserved = True

        size = Lookup.extract(self.data.get('size'), resource)

        # get existing tier
        model.sku = models.SkuDescription()
        model.sku.tier = resource['sku']['tier']
        model.sku.name = resource['sku']['name']

        if 'size' in self.data:
            model.sku.tier = ResizePlan.get_sku_name(size)
            model.sku.name = size

        if 'count' in self.data:
            model.sku.capacity = Lookup.extract(self.data.get('count'), resource)

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
