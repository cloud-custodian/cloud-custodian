# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
import json
import logging
import os
import time

from c7n.vendored.distutils.util import strtobool
import requests
from c7n_azure.constants import (
    AUTH_TYPE_MSI,
    AUTH_TYPE_UAI,
    AUTH_TYPE_EMBED,
    ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION,
    FUNCTION_EVENT_TRIGGER_MODE,
    FUNCTION_TIME_TRIGGER_MODE,
    FUNCTION_HOST_CONFIG,
    FUNCTION_EXTENSION_BUNDLE_CONFIG)
from c7n_azure.session import Session

from c7n.mu import PythonPackageArchive
from c7n.utils import local_session, jmespath_search


class AzurePythonPackageArchive(PythonPackageArchive):
    def __init__(self, modules=(), cache_file=None):
        super(AzurePythonPackageArchive, self).__init__(modules, cache_file)
        self.package_time = time.gmtime()

    def create_zinfo(self, file):
        """
        In Dedicated App Service Plans - Functions are updated via KuduSync
        KuduSync uses the modified time and file size to determine if a file has changed
        """
        info = super(AzurePythonPackageArchive, self).create_zinfo(file)
        info.date_time = self.package_time[0:6]
        return info


class FunctionPackage:
    log = logging.getLogger('custodian.azure.function_package.FunctionPackage')

    def __init__(self, name, function_path=None, target_sub_ids=None, cache_override_path=None):
        self.pkg = None
        self.name = name
        self.function_path = function_path or os.path.join(
            os.path.dirname(os.path.realpath(__file__)), 'function.py')
        self.cache_override_path = cache_override_path
        self.enable_ssl_cert = not strtobool(
            os.environ.get(ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION, 'no'))

        if target_sub_ids is not None:
            self.target_sub_ids = target_sub_ids
        else:
            self.target_sub_ids = [None]

        if not self.enable_ssl_cert:
            self.log.warning('SSL Certificate Validation is disabled')

    def _add_functions_required_files(
            self, policy_data, requirements, queue_name=None, identity=None):
        s = local_session(Session)

        self.pkg.add_contents(dest='requirements.txt',
                              contents=requirements)

        for target_sub_id in self.target_sub_ids:
            name = self.name + ("_" + target_sub_id if target_sub_id else "")
            # generate and add auth if using embedded service principal
            identity = (identity
                or jmespath_search(
                    'mode."provision-options".identity', policy_data)
                or {'type': AUTH_TYPE_EMBED})

            if identity['type'] == AUTH_TYPE_EMBED:
                auth_contents = s.get_functions_auth_string(target_sub_id)
            elif identity['type'] == AUTH_TYPE_MSI:
                auth_contents = json.dumps({
                    'use_msi': True, 'subscription_id': target_sub_id,
                    'tenant_id': s.get_tenant_id()})
            elif identity['type'] == AUTH_TYPE_UAI:
                auth_contents = json.dumps({
                    'use_msi': True, 'subscription_id': target_sub_id,
                    'client_id': identity['client_id'],
                    'tenant_id': s.get_tenant_id()})

            self.pkg.add_contents(dest=name + '/auth.json', contents=auth_contents)
            self.pkg.add_file(self.function_path,
                              dest=name + '/function.py')

            self.pkg.add_contents(dest=name + '/__init__.py', contents='')

            if policy_data:
                self.pkg.add_contents(
                    dest=name + '/function.json',
                    contents=self.get_function_config(policy_data, queue_name))
                self.pkg.add_contents(
                    dest=name + '/config.json',
                    contents=json.dumps({'policies': [policy_data]}, indent=2))
                self._add_host_config(policy_data['mode']['type'])
            else:
                self._add_host_config(None)

    def _add_host_config(self, mode):
        config = copy.deepcopy(FUNCTION_HOST_CONFIG)
        if mode == FUNCTION_EVENT_TRIGGER_MODE:
            config['extensionBundle'] = FUNCTION_EXTENSION_BUNDLE_CONFIG
        self.pkg.add_contents(dest='host.json', contents=json.dumps(config))

    def get_function_config(self, policy, queue_name=None):
        config = \
            {
                "scriptFile": "function.py",
                "bindings": [{
                    "direction": "in"
                }]
            }

        mode_type = policy['mode']['type']
        binding = config['bindings'][0]

        if mode_type == FUNCTION_TIME_TRIGGER_MODE:
            binding['type'] = 'timerTrigger'
            binding['name'] = 'input'
            binding['schedule'] = policy['mode']['schedule']

        elif mode_type == FUNCTION_EVENT_TRIGGER_MODE:
            binding['type'] = 'queueTrigger'
            binding['connection'] = 'AzureWebJobsStorage'
            binding['name'] = 'input'
            binding['queueName'] = queue_name

        else:
            self.log.error("Mode not yet supported for Azure functions (%s)"
                           % mode_type)

        return json.dumps(config, indent=2)

    @property
    def cache_folder(self):
        if self.cache_override_path:
            return self.cache_override_path

        c7n_azure_root = os.path.dirname(__file__)
        return os.path.join(c7n_azure_root, 'cache')

    def build(self, policy, modules, requirements, queue_name=None, identity=None):
        self.pkg = AzurePythonPackageArchive()

        self.pkg.add_modules(None,
                             [m.replace('-', '_') for m in modules])

        # add config and policy
        self._add_functions_required_files(policy, requirements, queue_name, identity)

    def wait_for_status(self, deployment_creds, retries=10, delay=15):
        for r in range(retries):
            if self.status(deployment_creds):
                return True
            else:
                self.log.info('(%s/%s) Will retry Function App status check in %s seconds...'
                              % (r + 1, retries, delay))
                time.sleep(delay)
        return False

    def status(self, deployment_creds):
        status_url = '%s/api/deployments' % deployment_creds.scm_uri

        r = requests.get(status_url, verify=self.enable_ssl_cert, timeout=60)
        if r.status_code != 200:
            self.log.error("Application service returned an error.\n%s\n%s"
                           % (r.status_code, r.text))
            return False

        return True

    def publish(self, deployment_creds):
        self.close()
        # update perms of the package
        os.chmod(self.pkg.path, 0o0644)

        zip_api_url = '%s/api/zipdeploy?isAsync=true&synctriggers=true' % deployment_creds.scm_uri
        headers = {'content-type': 'application/octet-stream'}
        self.log.info("Publishing Function package from %s" % self.pkg.path)

        zip_file = self.pkg.get_bytes()

        try:
            r = requests.post(zip_api_url,
                              data=zip_file,
                              headers=headers,
                              timeout=300,
                              verify=self.enable_ssl_cert)
        except requests.exceptions.ReadTimeout:
            self.log.error("Your Function App deployment timed out after 5 minutes. Try again.")

        r.raise_for_status()

        self.log.info("Function publish result: %s" % r.status_code)

    def close(self):
        self.pkg.close()
