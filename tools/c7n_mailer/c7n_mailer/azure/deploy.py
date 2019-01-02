# Copyright 2016-2017 Capital One Services, LLC
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
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import copy
import json
import logging
import os

try:
    from c7n_azure.function_package import FunctionPackage
    from c7n_azure.functionapp_utils import FunctionAppUtilities
    from c7n_azure.policy import AzureFunctionMode
    from c7n_azure.session import Session
    from c7n_azure.utils import StringUtils
    from c7n.utils import local_session
except ImportError:
    FunctionPackage = None
    pass


def build_function_package(config, function_name):
    schedule = config.get('function_schedule', '0 */10 * * * *')

    # Build package
    package = FunctionPackage(
        function_name,
        os.path.join(os.path.dirname(__file__), 'function.py'))

    package.build(None,
                  modules=['c7n', 'c7n-azure', 'c7n-mailer'],
                  non_binary_packages=['pyyaml', 'pycparser', 'tabulate',
                                       'datadog', 'MarkupSafe', 'simplejson'],
                  excluded_packages=['azure-cli-core', 'distlib', 'futures'])

    package.pkg.add_contents(
        function_name + '/function.json',
        contents=package.get_function_config({'mode':
                                              {'type': 'azure-periodic',
                                               'schedule': schedule}}))

    # Add mail templates
    for d in set(config['templates_folders']):
        if not os.path.exists(d):
            continue
        for t in [f for f in os.listdir(d) if os.path.splitext(f)[1] == '.j2']:
            with open(os.path.join(d, t)) as fh:
                package.pkg.add_contents(function_name + '/msg-templates/%s' % t, fh.read())

    function_config = copy.deepcopy(config)
    function_config['templates_folders'] = [function_name + '/msg-templates/']
    package.pkg.add_contents(
        function_name + '/config.json',
        contents=json.dumps(function_config))

    package.close()
    return package


def provision(config):
    log = logging.getLogger('c7n_mailer.azure.deploy')

    function_name = config.get('function_name', 'mailer')
    function_properties = config.get('function_properties', {})

    # service plan is parse first, because its location might be shared with storage & insights
    service_plan = AzureFunctionMode.extract_properties(function_properties,
                                                'servicePlan',
                                                {'name': 'cloud-custodian',
                                                 'location': 'westus2',
                                                 'resource_group_name': 'cloud-custodian',
                                                 'sku_name': 'B1',
                                                 'sku_tier': 'Basic'})

    location = service_plan.get('location', 'westus2')
    rg_name = service_plan['resource_group_name']

    sub_id = local_session(Session).get_subscription_id()
    suffix = StringUtils.naming_hash(rg_name + sub_id)

    storage_account = AzureFunctionMode.extract_properties(function_properties,
                                                    'storageAccount',
                                                    {'name': 'mailerstorage' + suffix,
                                                     'location': location,
                                                     'resource_group_name': rg_name})

    app_insights = AzureFunctionMode.extract_properties(function_properties,
                                                    'appInsights',
                                                    {'name': service_plan['name'],
                                                     'location': location,
                                                     'resource_group_name': rg_name})

    function_app_name = \
        '-'.join([service_plan['name'], function_name, suffix]) \
        .replace(' ', '-').lower()

    params = FunctionAppUtilities.FunctionAppInfrastructureParameters(
        app_insights=app_insights,
        service_plan=service_plan,
        storage_account=storage_account,
        function_app_resource_group_name=service_plan['resource_group_name'],
        function_app_name=function_app_name)

    FunctionAppUtilities().deploy_dedicated_function_app(params)

    log.info("Building function package for %s" % function_app_name)
    package = build_function_package(config, function_name)

    log.info("Function package built, size is %dMB" % (package.pkg.size / (1024 * 1024)))

    client = local_session(Session).client('azure.mgmt.web.WebSiteManagementClient')
    publish_creds = client.web_apps.list_publishing_credentials(
        service_plan['resource_group_name'],
        function_app_name).result()

    if package.wait_for_status(publish_creds):
        package.publish(publish_creds)
    else:
        log.error("Aborted deployment, ensure Application Service is healthy.")
