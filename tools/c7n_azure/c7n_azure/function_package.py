# Copyright 2018 Capital One Services, LLC
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
import copy
import json
import logging
import os
import time

import distutils.util
import requests
from c7n_azure.constants import (ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION,
                                 FUNCTION_EVENT_TRIGGER_MODE,
                                 FUNCTION_TIME_TRIGGER_MODE,
                                 FUNCTION_HOST_CONFIG,
                                 FUNCTION_EXTENSION_BUNDLE_CONFIG)
from c7n_azure.session import Session

from c7n.mu import PythonPackageArchive
from c7n.utils import local_session


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


class FunctionPackage(object):
    log = logging.getLogger('custodian.azure.function_package.FunctionPackage')

    def __init__(self, name, function_path=None, target_sub_ids=None, cache_override_path=None):
        self.pkg = None
        self.name = name
        self.function_path = function_path or os.path.join(
            os.path.dirname(os.path.realpath(__file__)), 'function.py')
        self.cache_override_path = cache_override_path
        self.enable_ssl_cert = not distutils.util.strtobool(
            os.environ.get(ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION, 'no'))

        if target_sub_ids is not None:
            self.target_sub_ids = target_sub_ids
        else:
            self.target_sub_ids = [None]

        if not self.enable_ssl_cert:
            self.log.warning('SSL Certificate Validation is disabled')

    def _add_functions_required_files(self, policy, requirements, queue_name=None):
        s = local_session(Session)

        self.pkg.add_contents(dest='requirements.txt',
                              contents=requirements)

        for target_sub_id in self.target_sub_ids:
            name = self.name + ("_" + target_sub_id if target_sub_id else "")
            # generate and add auth
            self.pkg.add_contents(dest=name + '/auth.json',
                                  contents=s.get_functions_auth_string(target_sub_id))

            self.pkg.add_file(self.function_path,
                              dest=name + '/function.py')

            self.pkg.add_contents(dest=name + '/__init__.py', contents='')

            if policy:
                config_contents = self.get_function_config(policy, queue_name)
                policy_contents = self._get_policy(policy)
                self.pkg.add_contents(dest=name + '/function.json',
                                      contents=config_contents)

                self.pkg.add_contents(dest=name + '/config.json',
                                      contents=policy_contents)
                self._add_host_config(policy['mode']['type'])
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

    def _get_policy(self, policy):
        return json.dumps({'policies': [policy]}, indent=2)

    def _update_perms_package(self):
        os.chmod(self.pkg.path, 0o0644)

    @property
    def cache_folder(self):
        if self.cache_override_path:
            return self.cache_override_path

        c7n_azure_root = os.path.dirname(__file__)
        return os.path.join(c7n_azure_root, 'cache')

    def build(self, policy, modules, requirements, queue_name=None):
        self.pkg = AzurePythonPackageArchive()

        self.pkg.add_modules(None,
                             [m.replace('-', '_') for m in modules])

        # add config and policy
        self._add_functions_required_files(policy, requirements, queue_name)

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

        r = requests.get(status_url, verify=self.enable_ssl_cert)
        if r.status_code != 200:
            self.log.error("Application service returned an error.\n%s\n%s"
                           % (r.status_code, r.text))
            return False

        return True

    def publish(self, deployment_creds):
        self.close()

        # update perms of the package
        self._update_perms_package()
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

    def wait_for_remote_build(self, deployment_creds, is_consumption):
        self.log.info('Waiting for the remote build to finish')

        # Replicate the behavior from azure core func tool.. Some racing in kudulight,
        # so different way to get the status. https://bit.ly/32AM71b
        if not is_consumption:
            is_deploying = True
            is_deploying_uri = '%s/api/isdeploying' % deployment_creds.scm_uri
            while is_deploying != 'False':
                self.log.info('Waiting for deployment to complete...')
                is_deploying = requests.get(is_deploying_uri).json()['value']
                time.sleep(10)

        # Get deployment id
        deployments_uri = '%s/deployments' % deployment_creds.scm_uri
        r = requests.get(deployments_uri).json()
        deployment_id = r[0]['id']

        status_uri = '%s/deployments/%s' % (deployment_creds.scm_uri, deployment_id)
        status_decoding = ['Pending', 'Building', 'Deploying', 'Failed', 'Success']
        while True:
            status = requests.get(status_uri).json()['status']
            if status == 3 or status == 4:
                break
            self.log.info('Deployment status: %s', status_decoding[status])
            time.sleep(10)

        if status == 3:
            log_uri = '%s/log' % status_uri
            self.log.error("Remote build failed. You can retrieve logs here: %s", log_uri)
            return False
        return True

    def close(self):
        self.pkg.close()
