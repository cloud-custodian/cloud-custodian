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

from azure.mgmt.web.models import (Site, SiteConfig)
from c7n_azure.constants import (FUNCTION_DOCKER_VERSION, FUNCTION_EXT_VERSION)
from c7n_azure.provisioning.deployment_unit import DeploymentUnit
from c7n_azure.utils import azure_name_value_pair


class FunctionAppDeploymentUnit(DeploymentUnit):

    def __init__(self):
        super(FunctionAppDeploymentUnit, self).__init__(
            'azure.mgmt.web.WebSiteManagementClient')
        self.type = "Function Application"

    def _get(self, params):
        return self.client.web_apps.get(params['resource_group_name'], params['name'])

    def _provision(self, params):
        site_config = SiteConfig(app_settings=[])
        functionapp_def = Site(
            https_only=True,
            client_cert_enabled=True,
            location=params['location'],
            site_config=site_config)

        # common function app settings
        functionapp_def.server_farm_id = params['app_service_plan_id']
        functionapp_def.reserved = True  # This implies Linux for auto-created app plans

        # consumption app plan
        if params['is_consumption_plan']:
            functionapp_def.kind = 'functionapp,linux'
        # dedicated app plan
        else:
            functionapp_def.kind = 'functionapp,linux,container'
            site_config.linux_fx_version = FUNCTION_DOCKER_VERSION
            site_config.always_on = True

        # application insights settings
        app_insights_key = params['app_insights_key']
        if app_insights_key:
            site_config.app_settings.append(
                azure_name_value_pair('APPINSIGHTS_INSTRUMENTATIONKEY', app_insights_key))

        # Don't generate pycache
        site_config.app_settings.append(
            azure_name_value_pair('PYTHONDONTWRITEBYTECODE', 1))

        # Enable server side build
        site_config.app_settings.append(
            azure_name_value_pair('ENABLE_ORYX_BUILD', 'true')
        )
        site_config.app_settings.append(
            azure_name_value_pair('SCM_DO_BUILD_DURING_DEPLOYMENT', 'true')
        )

        # general app settings
        con_string = params['storage_account_connection_string']
        site_config.app_settings.append(azure_name_value_pair('AzureWebJobsStorage', con_string))
        site_config.app_settings.append(azure_name_value_pair('FUNCTIONS_EXTENSION_VERSION',
                                                              FUNCTION_EXT_VERSION))
        site_config.app_settings.append(azure_name_value_pair('FUNCTIONS_WORKER_RUNTIME', 'python'))

        return self.client.web_apps.create_or_update(params['resource_group_name'],
                                                     params['name'],
                                                     functionapp_def).result()
