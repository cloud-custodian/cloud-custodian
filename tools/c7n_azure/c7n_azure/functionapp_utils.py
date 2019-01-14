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
import datetime
import logging
import time

from azure.storage.blob import BlobPermissions
from c7n_azure.constants import \
    FUNCTION_CONSUMPTION_BLOB_CONTAINER, FUNCTION_PACKAGE_SAS_EXPIRY_DAYS
from c7n_azure.provisioning.app_insights import AppInsightsUnit
from c7n_azure.provisioning.app_service_plan import AppServicePlanUnit
from c7n_azure.provisioning.function_app import FunctionAppDeploymentUnit
from c7n_azure.provisioning.storage_account import StorageAccountUnit
from c7n_azure.session import Session
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.utils import ResourceIdParser, StringUtils
from msrestazure.azure_exceptions import CloudError

from c7n.utils import local_session


class FunctionAppUtilities(object):
    log = logging.getLogger('custodian.azure.function_app_utils')

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
    def is_consumption_plan(function_params):
        return StringUtils.equal(function_params.service_plan['sku_tier'], 'dynamic')

    @staticmethod
    def deploy_function_app(parameters):
        function_app_unit = FunctionAppDeploymentUnit()
        function_app_params = \
            {'name': parameters.function_app_name,
             'resource_group_name': parameters.function_app_resource_group_name}
        function_app = function_app_unit.get(function_app_params)

        if function_app:
            # retrieve the type of app service plan hosting the existing function app
            session = local_session(Session)
            web_client = session.client('azure.mgmt.web.WebSiteManagementClient')
            app_id = function_app.server_farm_id
            app_name = ResourceIdParser.get_resource_name(app_id)
            app_resource_group_name = ResourceIdParser.get_resource_group(app_id)
            app_service_plan = web_client.app_service_plans.get(app_resource_group_name, app_name)

            # update the sku tier to properly reflect what is provisioned in Azure
            parameters.service_plan['sku_tier'] = app_service_plan.sku.tier

            return function_app

        sp_unit = AppServicePlanUnit()
        app_service_plan = sp_unit.provision_if_not_exists(parameters.service_plan)

        # if only resource_id is provided, retrieve existing app plan sku tier
        parameters.service_plan['sku_tier'] = app_service_plan.sku.tier

        ai_unit = AppInsightsUnit()
        app_insights = ai_unit.provision_if_not_exists(parameters.app_insights)

        sa_unit = StorageAccountUnit()
        storage_account_id = sa_unit.provision_if_not_exists(parameters.storage_account).id
        con_string = FunctionAppUtilities.get_storage_account_connection_string(storage_account_id)

        function_app_params.update(
            {'location': app_service_plan.location,
             'app_service_plan_id': app_service_plan.id,
             'app_insights_key': app_insights.instrumentation_key,
             'is_consumption_plan': FunctionAppUtilities.is_consumption_plan(parameters),
             'storage_account_connection_string': con_string})

        return function_app_unit.provision(function_app_params)

    @classmethod
    def publish_functions_package(cls, function_params, package):
        session = local_session(Session)
        web_client = session.client('azure.mgmt.web.WebSiteManagementClient')

        cls.log.info('Publishing Function application')

        # provision using Kudu Zip-Deploy
        if not cls.is_consumption_plan(function_params):
            publish_creds = web_client.web_apps.list_publishing_credentials(
                function_params.function_app_resource_group_name,
                function_params.function_app_name).result()

            if package.wait_for_status(publish_creds):
                package.publish(publish_creds)
            else:
                cls.log.error("Aborted deployment, ensure Application Service is healthy.")
        # provision using WEBSITE_RUN_FROM_PACKAGE
        else:
            # fetch blob client
            blob_client = StorageUtilities.get_blob_client_from_storage_account(
                function_params.storage_account['resource_group_name'],
                function_params.storage_account['name'],
                session,
                sas_generation=True
            )

            # create container for package
            blob_client.create_container(FUNCTION_CONSUMPTION_BLOB_CONTAINER)

            # upload package
            blob_name = '%s.zip' % function_params.function_app_name
            blob_client.create_blob_from_path(
                FUNCTION_CONSUMPTION_BLOB_CONTAINER, blob_name, package.pkg.path)

            # create blob url for package
            sas = blob_client.generate_blob_shared_access_signature(
                FUNCTION_CONSUMPTION_BLOB_CONTAINER,
                blob_name,
                BlobPermissions.READ,
                datetime.datetime.utcnow() +
                datetime.timedelta(days=FUNCTION_PACKAGE_SAS_EXPIRY_DAYS)
                # expire in 10 years
            )
            blob_url = blob_client.make_blob_url(
                FUNCTION_CONSUMPTION_BLOB_CONTAINER,
                blob_name,
                sas_token=sas)

            # update application settings function package
            app_settings = web_client.web_apps.list_application_settings(
                function_params.function_app_resource_group_name,
                function_params.function_app_name)
            app_settings.properties['WEBSITE_RUN_FROM_PACKAGE'] = blob_url
            web_client.web_apps.update_application_settings(
                function_params.function_app_resource_group_name,
                function_params.function_app_name,
                kind=str,
                properties=app_settings.properties
            )

        # sync the scale controller for the Function App
        if not cls._sync_function_triggers(function_params):
            cls.log.error("Unable to sync triggers...")

        cls.log.info('Finished publishing Function application')

    @classmethod
    def _sync_function_triggers(cls, function_params):
        cls.log.info('Sync Triggers...')
        session = local_session(Session)
        web_client = session.client('azure.mgmt.web.WebSiteManagementClient')

        max_retry_attempts = 3
        for r in range(max_retry_attempts):
            res = None
            try:
                res = web_client.web_apps.sync_function_triggers(
                    function_params.function_app_resource_group_name,
                    function_params.function_app_name
                )
            except CloudError as e:
                # This appears to be a bug in the API
                # Success can be either 200 or 204, which is
                # unexpected and gets rethrown as a CloudError
                if e.response.status_code in [200, 204]:
                    return True

                cls.log.error("Failed to sync triggers...")
                cls.log.error(e)

            if res and res.status_code in [200, 204]:
                return True
            else:
                cls.log.info("Retrying in 5 seconds...")
                time.sleep(5)

        return False
