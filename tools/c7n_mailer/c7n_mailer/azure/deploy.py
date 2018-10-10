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
    from c7n_azure.template_utils import TemplateUtilities
    from c7n_azure.constants import CONST_DOCKER_VERSION, CONST_FUNCTIONS_EXT_VERSION
except ImportError:
    FunctionPackage = TemplateUtilities = None
    CONST_DOCKER_VERSION = CONST_FUNCTIONS_EXT_VERSION = None
    pass


def provision(config):
    log = logging.getLogger('c7n_mailer.azure.deploy')

    function_name = config.get('function_name', 'mailer')

    func_config = dict(
        name=function_name,
        servicePlanName=config.get('function_servicePlanName', 'cloudcustodian'),
        location=config.get('function_location'),
        appInsightsLocation=config.get('function_appInsightsLocation'),
        schedule=config.get('function_schedule', '0 */10 * * * *'),
        skuCode=config.get('function_skuCode'),
        sku=config.get('function_sku'))

    template_util = TemplateUtilities()

    parameters = _get_parameters(template_util, func_config)
    group_name = parameters['servicePlanName']['value']
    webapp_name = parameters['name']['value']

    # Check if already existing
    existing_webapp = template_util.resource_exist(group_name, webapp_name)

    # Deploy
    if not existing_webapp:
        template_util.create_resource_group(
            group_name, {'location': parameters['location']['value']})

        template_util.deploy_resource_template(
            group_name, 'dedicated_functionapp.json', parameters).wait()
    else:
        log.info("Found existing App %s (%s) in group %s" %
                 (webapp_name, existing_webapp.location, group_name))

    log.info("Building function package for %s" % webapp_name)

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
                                               'schedule': func_config['schedule']}}))
    # Add mail templates
    template_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '../..', 'msg-templates'))

    for t in os.listdir(template_dir):
        with open(os.path.join(template_dir, t)) as fh:
            packager.pkg.add_contents('msg-templates/%s' % t, fh.read())

    packager.close()

    if packager.wait_for_status(webapp_name):
        packager.publish(webapp_name)
    else:
        log.error("Aborted deployment, ensure Application Service is healthy.")


def _get_parameters(template_util, func_config):
    parameters = template_util.get_default_parameters(
        'dedicated_functionapp.parameters.json')

    func_config['name'] = (func_config['servicePlanName'] + '-' +
                           func_config['name']).replace(' ', '-').lower()

    func_config['storageName'] = (func_config['servicePlanName']).replace('-', '')
    func_config['dockerVersion'] = CONST_DOCKER_VERSION
    func_config['functionsExtVersion'] = CONST_FUNCTIONS_EXT_VERSION
    func_config['machineDecryptionKey'] = FunctionAppUtilities.generate_machine_decryption_key()

    parameters = template_util.update_parameters(parameters, func_config)

    return parameters
