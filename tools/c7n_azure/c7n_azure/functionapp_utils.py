# Copyright 2015-2018 Capital One Services, LLC
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

import logging
import os
from binascii import hexlify

from azure.mgmt.web.models import (AppServicePlan, NameValuePair, Site,
                                   SiteConfig, SkuDescription)

from c7n.utils import local_session

from c7n_azure.session import Session

from c7n_azure.provisioning.app_insights import AppInsightsUnit
from c7n_azure.provisioning.app_service_plan import AppServicePlanUnit
from c7n_azure.provisioning.storage_account import StorageAccountUnit
from c7n_azure.provisioning.webapp import WebAppDeploymentUnit
from c7n_azure.utils import ResourceIdParser


class FunctionAppUtilities(object):
    def __init__(self):
        self.local_session = local_session(Session)
        self.log = logging.getLogger('custodian.azure.function_app_utils')

    class FunctionAppInfrastructureParameters:
        def __init__(self, appInsights, servicePlan, storageAccount, webapp_name):
            self.appInsights = appInsights
            self.servicePlan = servicePlan
            self.storageAccount = storageAccount
            self.webapp_name = webapp_name

    @staticmethod
    def get_storage_account_connection_string(id):
        rg_name = ResourceIdParser.get_resource_group(id)
        name = ResourceIdParser.get_resource_name(id)
        client = local_session(Session).client('azure.mgmt.storage.StorageManagementClient')
        obj = client.storage_accounts.list_keys(rg_name, name)

        connection_string = 'DefaultEndpointsProtocol={};AccountName={};AccountKey={}'.format(
            'https',
            name,
            obj.keys[0].value)

        return connection_string


    def deploy_webapp(self, parameters):

        web_app_unit = WebAppDeploymentUnit()
        web_app_params = {'name': parameters.webapp_name,
                          'resource_group_name': parameters.servicePlan['resource_group_name']}
        web_app = web_app_unit.get(web_app_params)
        if web_app:
            return web_app

        sp_unit = AppServicePlanUnit()
        app_service_plan = sp_unit.provision_if_not_exists(parameters.servicePlan)

        ai_unit = AppInsightsUnit()
        app_insights = ai_unit.provision_if_not_exists(parameters.appInsights)

        sa_unit = StorageAccountUnit()
        storage_account_id = sa_unit.provision_if_not_exists(parameters.storageAccount).id

        web_app_params.update({'location': app_service_plan.location,
                               'app_service_plan_id': app_service_plan.id,
                               'app_insights_key': app_insights.instrumentation_key,
                               'storage_account_connection_string': FunctionAppUtilities.get_storage_account_connection_string(storage_account_id)})

        return web_app_unit.provision(web_app_params)