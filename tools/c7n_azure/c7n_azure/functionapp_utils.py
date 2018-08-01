import logging

from azure.mgmt.web.models import (Site, SiteConfig, NameValuePair)
from c7n_azure.session import Session
from c7n_azure.constants import CONST_DOCKER_VERSION, CONST_FUNCTIONS_EXT_VERSION

from c7n.utils import local_session


class FunctionAppUtilities(object):
    def __init__(self):
        self.local_session = local_session(Session)
        self.log = logging.getLogger('custodian.azure.function_app_utils')

    def deploy_webapp(self, app_name, group_name, service_plan, storage_account_name):
        self.log.info("Deploying Function App %s (%s) in group %s" %
                      (app_name, service_plan.location, group_name))

        site_config = SiteConfig(app_settings=[])
        functionapp_def = Site(location=service_plan.location, site_config=site_config)

        functionapp_def.kind = 'functionapp,linux'
        functionapp_def.server_farm_id = service_plan.id

        site_config.linux_fx_version = CONST_DOCKER_VERSION
        site_config.always_on = True

        app_insights_key = self.get_application_insights_key(group_name,
                                                             service_plan.app_service_plan_name)

        if app_insights_key:
            site_config.app_settings.append(
                NameValuePair('APPINSIGHTS_INSTRUMENTATIONKEY', app_insights_key))

        con_string = self.get_storage_connection_string(group_name, storage_account_name)
        site_config.app_settings.append(NameValuePair('AzureWebJobsStorage', con_string))
        site_config.app_settings.append(NameValuePair('AzureWebJobsDashboard', con_string))
        site_config.app_settings.append(NameValuePair('FUNCTIONS_EXTENSION_VERSION',
                                                      CONST_FUNCTIONS_EXT_VERSION))
        site_config.app_settings.append(NameValuePair('FUNCTIONS_WORKER_RUNTIME', 'python'))

        #: :type: azure.mgmt.web.WebSiteManagementClient
        web_client = self.local_session.client('azure.mgmt.web.WebSiteManagementClient')
        web_client.web_apps.create_or_update(group_name, app_name, functionapp_def).wait()

    def get_storage_connection_string(self, resource_group_name, storage_account_name):
        #: :type: azure.mgmt.web.WebSiteManagementClient
        storage_client = self.local_session.client('azure.mgmt.storage.StorageManagementClient')

        obj = storage_client.storage_accounts.list_keys(resource_group_name,
                                                        storage_account_name)

        connection_string = 'DefaultEndpointsProtocol={};AccountName={};AccountKey={}'.format(
            'https',
            storage_account_name,
            obj.keys[0].value)

        return connection_string

    def get_application_insights_key(self, resource_group_name, application_insights_name):
        #: :type: azure.mgmt.applicationinsights.ApplicationInsightsManagementClient
        insights_client = self.local_session.client(
            'azure.mgmt.applicationinsights.ApplicationInsightsManagementClient')

        try:
            app_insights = insights_client.components.get(resource_group_name,
                                                      application_insights_name)
            return app_insights.instrumentation_key

        except Exception:
            return False
