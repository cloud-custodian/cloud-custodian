# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import re

from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser, StringUtils
from c7n.utils import local_session

from c7n_azure.provisioning.app_insights import AppInsightsUnit
from c7n_azure.provisioning.app_service_plan import AppServicePlanUnit
from c7n_azure.provisioning.function_app import FunctionAppDeploymentUnit
from c7n_azure.provisioning.storage_account import StorageAccountUnit


class FunctionAppUtilities:
    log = logging.getLogger('custodian.azure.function_app_utils')

    class FunctionAppInfrastructureParameters:
        def __init__(self, app_insights, service_plan, storage_account,
                     function_app):
            self.app_insights = app_insights
            self.service_plan = service_plan
            self.storage_account = storage_account
            self.function_app = function_app

    @staticmethod
    def get_storage_account_connection_string(id):
        rg_name = ResourceIdParser.get_resource_group(id)
        name = ResourceIdParser.get_resource_name(id)
        client = local_session(Session).client('azure.mgmt.storage.StorageManagementClient')
        obj = client.storage_accounts.list_keys(rg_name, name, expand=None)

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
        function_app_params = dict(parameters.function_app)
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

    @staticmethod
    def validate_function_name(function_name):
        if (function_name is None or len(function_name) > 60 or len(function_name) < 1):
            raise ValueError('Function name must be between 1-60 characters. Given name: "' +
                             str(function_name) + '"')

    @staticmethod
    def get_function_name(policy_name, suffix):
        function_app_name = policy_name + '-' + suffix
        return re.sub('[^A-Za-z0-9\\-]', '-', function_app_name)

    @classmethod
    def publish_functions_package(cls, function_params, package):
        session = local_session(Session)
        web_client = session.client('azure.mgmt.web.WebSiteManagementClient')

        cls.log.info('Publishing Function application')

        publish_creds = web_client.web_apps.begin_list_publishing_credentials(
            function_params.function_app['resource_group_name'],
            function_params.function_app['name']).result()

        if package.wait_for_status(publish_creds):
            package.publish(publish_creds)
            cls.log.info('Finished publishing Function application')
        else:
            cls.log.error("Aborted deployment, ensure Application Service is healthy.")
