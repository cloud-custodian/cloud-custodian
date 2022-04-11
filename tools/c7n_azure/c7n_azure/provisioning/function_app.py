# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.web.models import (
    Site,
    SiteConfig,
    ManagedServiceIdentity)

from c7n_azure.constants import (AUTH_TYPE_EMBED, FUNCTION_DOCKER_VERSION, FUNCTION_EXT_VERSION)
from c7n_azure.provisioning.deployment_unit import DeploymentUnit
from c7n_azure.utils import azure_name_value_pair


class FunctionAppDeploymentUnit(DeploymentUnit):

    def __init__(self):
        super(FunctionAppDeploymentUnit, self).__init__(
            'azure.mgmt.web.WebSiteManagementClient')
        self.type = "Function Application"

    def _get(self, params):
        return self.client.web_apps.get(
            params['resource_group_name'], params['name'])

    def _get_identity(self, params):
        if 'identity' not in params:
            return
        if params['identity']['type'] == AUTH_TYPE_EMBED:
            return
        identity = ManagedServiceIdentity(type=params['identity']['type'])
        if 'id' in params['identity']:
            identity.user_assigned_identities = {
                params['identity']['id']: {}}
        return identity

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
        functionapp_def.identity = self._get_identity(params)

        # consumption app plan
        if params['is_consumption_plan']:
            functionapp_def.kind = 'functionapp,linux'
            site_config.linux_fx_version = FUNCTION_DOCKER_VERSION
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

        return self.client.web_apps.begin_create_or_update(params['resource_group_name'],
                                                           params['name'],
                                                           functionapp_def).result()
