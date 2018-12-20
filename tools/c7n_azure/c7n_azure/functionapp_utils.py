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
from collections import defaultdict

from c7n_azure.function_package import FunctionPackage

from c7n.utils import local_session

from c7n_azure.provisioning.app_insights import AppInsightsUnit
from c7n_azure.provisioning.app_service_plan import AppServicePlanUnit
from c7n_azure.provisioning.storage_account import StorageAccountUnit
from c7n_azure.provisioning.function_app import FunctionAppDeploymentUnit
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser, StringUtils


class FunctionAppUtilities(object):
    def __init__(self):
        self.log = logging.getLogger('custodian.azure.function_app_utils')

    class FunctionAppInfrastructureParameters:
        def __init__(self, app_insights, service_plan, storage_account,
                     function_app_resource_group_name, function_app_name):
            self.app_insights = app_insights
            self.service_plan = service_plan
            self.storage_account = storage_account
            self.function_app_resource_group_name = function_app_resource_group_name
            self.function_app_name = function_app_name

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

    @staticmethod
    def deploy_function_app(parameters):
        function_app_unit = FunctionAppDeploymentUnit()
        function_app_params = defaultdict(lambda: None)
        function_app_params.update({
            'name': parameters.function_app_name,
            'resource_group_name': parameters.function_app_resource_group_name,
            'location': parameters.service_plan['location']})

        function_app = function_app_unit.get(function_app_params)
        if function_app:
            return function_app

        # provision app plan for non-consumption Function apps
        if not StringUtils.equal(parameters.service_plan['tier'], 'dynamic'):
            sp_unit = AppServicePlanUnit()
            app_service_plan = sp_unit.provision_if_not_exists(parameters.service_plan)
            function_app_params.update({'location': app_service_plan.location,
                                        'app_service_plan_id': app_service_plan.id})

        ai_unit = AppInsightsUnit()
        app_insights = ai_unit.provision_if_not_exists(parameters.app_insights)

        sa_unit = StorageAccountUnit()
        storage_account_id = sa_unit.provision_if_not_exists(parameters.storage_account).id
        con_string = FunctionAppUtilities.get_storage_account_connection_string(storage_account_id)

        function_app_params.update({'app_insights_key': app_insights.instrumentation_key,
                                    'storage_account_connection_string': con_string})

        return function_app_unit.provision(function_app_params)

    def publish_functions_package(self, function_params, package):
        client = local_session(Session).client('azure.mgmt.web.WebSiteManagementClient')

        # provision using Kudu
        if not StringUtils.equal(function_params.service_plan['tier'], 'dynamic'):
            publish_creds = client.web_apps.list_publishing_credentials(
                self.function_params.function_app_resource_group_name,
                self.function_params.function_app_name).result()

            if package.wait_for_status(publish_creds):
                package.publish(publish_creds)
            else:
                self.log.error("Aborted deployment, ensure Application Service is healthy.")
        else:
            self.log.info("Consumption Plan")
