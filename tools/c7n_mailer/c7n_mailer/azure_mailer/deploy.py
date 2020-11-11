# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
import json
import logging
import os

import jmespath
from c7n_mailer.deploy import CORE_DEPS

try:
    from c7n.mu import generate_requirements
    from c7n_azure.constants import AUTH_TYPE_EMBED
    from c7n_azure.function_package import FunctionPackage
    from c7n_azure.functionapp_utils import FunctionAppUtilities
    from c7n_azure.policy import AzureFunctionMode
    from c7n_azure.session import Session
    from c7n_azure.utils import StringUtils
    from c7n.utils import local_session
except ImportError:
    FunctionPackage = None
    pass


def cache_path():
    return os.path.join(os.path.dirname(__file__), 'cache')


def get_mailer_requirements():
    deps = ['azure-keyvault', 'azure-storage-queue',
            'azure-storage-blob', 'sendgrid'] + list(CORE_DEPS)
    requirements = generate_requirements(
        deps, ignore=['boto3', 'botocore', 'pywin32'],
        include_self=True)
    return requirements


def build_function_package(config, function_name, sub_id):
    schedule = config.get('function_schedule', '0 */10 * * * *')

    cache_override_path = cache_path()

    function_path = function_name + "_" + sub_id

    # Build package
    package = FunctionPackage(
        function_name,
        os.path.join(os.path.dirname(__file__), 'function.py'),
        target_sub_ids=[sub_id],
        cache_override_path=cache_override_path)

    identity = jmespath.search('function_properties.identity', config)
    package.build(None,
                  modules=['c7n', 'c7n_azure', 'c7n_mailer'],
                  requirements=get_mailer_requirements(),
                  identity=identity)

    package.pkg.add_contents(
        function_path + '/function.json',
        contents=package.get_function_config({'mode':
                                              {'type': 'azure-periodic',
                                               'schedule': schedule}}))

    # Add mail templates
    for d in set(config['templates_folders']):
        if not os.path.exists(d):
            continue
        for t in [f for f in os.listdir(d) if os.path.splitext(f)[1] == '.j2']:
            with open(os.path.join(d, t)) as fh:
                package.pkg.add_contents(function_path + '/msg-templates/%s' % t, fh.read())

    function_config = copy.deepcopy(config)

    functions_full_template_path = '/home/site/wwwroot/' + function_path + '/msg-templates/'
    function_config['templates_folders'] = [functions_full_template_path]

    package.pkg.add_contents(
        function_path + '/config.json',
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
                                                {
                                                    'name': 'cloud-custodian',
                                                    'location': 'eastus',
                                                    'resource_group_name': 'cloud-custodian',
                                                    'sku_tier': 'Dynamic',  # consumption plan
                                                    'sku_name': 'Y1'
                                                })

    location = service_plan.get('location', 'eastus')
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

    function_app_name = FunctionAppUtilities.get_function_name(
        '-'.join([service_plan['name'], function_name]), suffix)
    FunctionAppUtilities.validate_function_name(function_app_name)

    params = FunctionAppUtilities.FunctionAppInfrastructureParameters(
        app_insights=app_insights,
        service_plan=service_plan,
        storage_account=storage_account,
        function_app={'resource_group_name': service_plan['resource_group_name'],
                      'identity': {'type': AUTH_TYPE_EMBED},
                      'name': function_app_name})

    FunctionAppUtilities.deploy_function_app(params)

    log.info("Building function package for %s" % function_app_name)
    package = build_function_package(config, function_name, sub_id)

    log.info("Function package built, size is %0.2f MB" % (package.pkg.size / (1024 * 1024.0)))

    FunctionAppUtilities.publish_functions_package(params, package)
