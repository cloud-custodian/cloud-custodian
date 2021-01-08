# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
from azure.mgmt.web.models import AppServicePlan, SkuDescription
from c7n_azure.provisioning.autoscale import AutoScaleUnit
from c7n_azure.provisioning.deployment_unit import DeploymentUnit
from c7n_azure.provisioning.resource_group import ResourceGroupUnit
from c7n_azure.utils import StringUtils


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

        plan_params = AppServicePlan(
            app_service_plan_name=params['name'],
            location=params['location'],
            sku=SkuDescription(
                name=params['sku_name'],
                capacity=1,
                tier=params['sku_tier']),
            kind='linux',
            target_worker_size_id=0,
            reserved=True)

        plan = self.client.app_service_plans.create_or_update(params['resource_group_name'],
                                                              params['name'],
                                                              plan_params).result()

        # Deploy default autoscale rule for dedicated plans if required by the policy
        autoscale_params = copy.deepcopy(params.get('auto_scale', {}))
        if bool(autoscale_params.get('enabled')) and \
           not StringUtils.equal(plan.sku, 'dynamic'):
            autoscale_params['name'] = 'autoscale'
            autoscale_params['resource_group_name'] = params['resource_group_name']
            autoscale_params['service_plan_id'] = plan.id
            autoscale_params['location'] = plan.location

            ac_unit = AutoScaleUnit()
            ac_unit.provision(autoscale_params)

        return plan
