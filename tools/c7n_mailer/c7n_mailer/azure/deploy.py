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
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import os
import logging

try:
    from c7n_azure.function_package import FunctionPackage
    from c7n_azure.functionapp_utils import FunctionAppUtilities
    from c7n_azure.constants import CONST_DOCKER_VERSION, CONST_FUNCTIONS_EXT_VERSION
    from c7n_azure.policy import AzureFunctionMode
except ImportError:
    FunctionPackage = None
    CONST_DOCKER_VERSION = CONST_FUNCTIONS_EXT_VERSION = None
    pass


def provision(config):
    log = logging.getLogger('c7n_mailer.azure.deploy')

    function_name = config.get('function_name', 'mailer')
    schedule = config.get('function_schedule', '0 */10 * * * *')
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
    storage_account = AzureFunctionMode.extract_properties(function_properties,
                                                    'storageAccount',
                                                    {'name': 'custodianstorageaccount',
                                                     'location': location,
                                                     'resource_group_name': rg_name})

    app_insights = AzureFunctionMode.extract_properties(function_properties,
                                                    'appInsights',
                                                    {'name': service_plan['name'],
                                                     'location': location,
                                                     'resource_group_name': rg_name})

    functionapp_name = (service_plan['name'] + '-' + function_name).replace(' ', '-').lower()

    params = FunctionAppUtilities.FunctionAppInfrastructureParameters(
        app_insights=app_insights,
        service_plan=service_plan,
        storage_account=storage_account,
        functionapp_name=functionapp_name)

    FunctionAppUtilities().deploy_dedicated_function_app(params)

    log.info("Building function package for %s" % functionapp_name)

    # Build package
    packager = FunctionPackage(
        function_name,
        os.path.join(os.path.dirname(__file__), 'function.py'))

    packager.build(None,
                   entry_point=os.path.join(os.path.dirname(__file__), 'handle.py'),
                   extra_modules={'c7n_mailer', 'ruamel'})

    packager.pkg.add_contents(
        function_name + '/config.json',
        contents=json.dumps(config))

    packager.pkg.add_contents(
        function_name + '/function.json',
        contents=packager.get_function_config({'mode':
                                              {'type': 'azure-periodic',
                                               'schedule': schedule}}))
    # Add mail templates
    template_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '../..', 'msg-templates'))

    for t in os.listdir(template_dir):
        with open(os.path.join(template_dir, t)) as fh:
            packager.pkg.add_contents('msg-templates/%s' % t, fh.read())

    packager.close()

    if packager.wait_for_status(functionapp_name):
        packager.publish(functionapp_name)
    else:
        log.error("Aborted deployment, ensure Application Service is healthy.")
