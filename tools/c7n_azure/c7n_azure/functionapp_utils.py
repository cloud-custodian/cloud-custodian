import logging

from azure.mgmt.web.models import (Site, SiteConfig, NameValuePair)
from c7n_azure.session import Session

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

        site_config.linux_fx_version = 'DOCKER|microsoft/azure-functions-python3.6:latest'
        site_config.always_on = True

        con_string = self.get_storage_connection_string(group_name, storage_account_name)

        site_config.app_settings.append(NameValuePair('AzureWebJobsStorage', con_string))
        site_config.app_settings.append(NameValuePair('AzureWebJobsDashboard', con_string))
        site_config.app_settings.append(NameValuePair('FUNCTIONS_EXTENSION_VERSION', 'beta'))
        site_config.app_settings.append(NameValuePair('FUNCTIONS_WORKER_RUNTIME', 'python'))

        #: :type: azure.mgmt.web.WebSiteManagementClient
        web_client = self.local_session.client('azure.mgmt.web.WebSiteManagementClient')
        web_client.web_apps.create_or_update(group_name, app_name, functionapp_def).wait()

    def get_storage_connection_string(self, resource_group_name, storage_account_name):
        #: :type: azure.mgmt.web.WebSiteManagementClient
        storage_client = self.local_session.client('azure.mgmt.storage.StorageManagementClient')

        obj = storage_client.storage_accounts.list_keys(resource_group_name,
                                                        storage_account_name)

        connection_string = 'DefaultEndpointsProtocol={};EndpointSuffix={};AccountName={};AccountKey={}'.format(
            'https',
            '2015-05-01-preview',
            storage_account_name,
            obj.keys[0].value)

        return connection_string
