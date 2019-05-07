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
import distutils.util
import json
import logging
import os
import shutil
import time

import requests

from c7n.mu import PythonPackageArchive
from c7n.utils import local_session
from c7n_azure.constants import (ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION,
                                 FUNCTION_EVENT_TRIGGER_MODE,
                                 FUNCTION_TIME_TRIGGER_MODE)
from c7n_azure.dependency_manager import DependencyManager
from c7n_azure.session import Session


class FunctionPackage(object):

    def __init__(self, name, function_path=None, target_subscription_ids=None):
        self.log = logging.getLogger('custodian.azure.function_package')
        self.pkg = None
        self.name = name
        self.function_path = function_path or os.path.join(
            os.path.dirname(os.path.realpath(__file__)), 'function.py')
        self.enable_ssl_cert = not distutils.util.strtobool(
            os.environ.get(ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION, 'no'))

        if target_subscription_ids is not None:
            self.target_subscription_ids = target_subscription_ids
        else:
            self.target_subscription_ids = [None]

        if not self.enable_ssl_cert:
            self.log.warning('SSL Certificate Validation is disabled')

    def _add_functions_required_files(self, policy, queue_name=None):
        s = local_session(Session)

        for target_subscription_id in self.target_subscription_ids:
            name = self.name + ("_" + target_subscription_id if target_subscription_id else "")
            # generate and add auth
            self.pkg.add_contents(dest=name + '/auth.json',
                                  contents=s.get_functions_auth_string(target_subscription_id))

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

                if policy['mode']['type'] == FUNCTION_EVENT_TRIGGER_MODE:
                    self._add_queue_binding_extensions()

        self._add_host_config()

    def _add_host_config(self):
        config = \
            {
                "version": "2.0",
                "healthMonitor": {
                    "enabled": True,
                    "healthCheckInterval": "00:00:10",
                    "healthCheckWindow": "00:02:00",
                    "healthCheckThreshold": 6,
                    "counterThreshold": 0.80
                },
                "functionTimeout": "00:05:00",
                "logging": {
                    "fileLoggingMode": "debugOnly"
                },
                "extensions": {
                    "http": {
                        "routePrefix": "api",
                        "maxConcurrentRequests": 5,
                        "maxOutstandingRequests": 30
                    }
                }
            }
        self.pkg.add_contents(dest='host.json', contents=json.dumps(config))

    def _add_queue_binding_extensions(self):
        bindings_dir_path = os.path.abspath(
            os.path.join(os.path.join(__file__, os.pardir), 'function_binding_resources'))
        bin_path = os.path.join(bindings_dir_path, 'bin')

        self.pkg.add_directory(bin_path)
        self.pkg.add_file(os.path.join(bindings_dir_path, 'extensions.csproj'))

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
        c7n_azure_root = os.path.dirname(__file__)
        return os.path.join(c7n_azure_root, 'cache')

    def build(self, policy, modules, non_binary_packages, excluded_packages, queue_name=None,):

        wheels_folder = os.path.join(self.cache_folder, 'wheels')
        wheels_install_folder = os.path.join(self.cache_folder, 'dependencies')

        cache_zip_file = os.path.join(self.cache_folder, 'cache.zip')
        cache_metadata_file = os.path.join(self.cache_folder, 'metadata.json')

        packages = \
            DependencyManager.get_dependency_packages_list(modules, excluded_packages)

        if not DependencyManager.check_cache(cache_metadata_file, cache_zip_file, packages):
            cache_pkg = PythonPackageArchive()
            self.log.info("Cached packages not found or requirements were changed.")
            # If cache check fails, wipe all previous wheels, installations etc
            if os.path.exists(self.cache_folder):
                self.log.info("Removing cache folder...")
                shutil.rmtree(self.cache_folder)

            self.log.info("Preparing non binary wheels...")
            DependencyManager.prepare_non_binary_wheels(non_binary_packages, wheels_folder)

            self.log.info("Downloading wheels...")
            DependencyManager.download_wheels(packages, wheels_folder)

            self.log.info("Installing wheels...")
            DependencyManager.install_wheels(wheels_folder, wheels_install_folder)

            for root, _, files in os.walk(wheels_install_folder):
                arc_prefix = os.path.relpath(root, wheels_install_folder)
                for f in files:
                    dest_path = os.path.join(arc_prefix, f)

                    if f.endswith('.pyc') or f.endswith('.c'):
                        continue
                    f_path = os.path.join(root, f)

                    cache_pkg.add_file(f_path, dest_path)

            self.log.info('Saving cache zip file...')
            cache_pkg.close()
            with open(cache_zip_file, 'wb') as fout:
                fout.write(cache_pkg.get_stream().read())

            self.log.info("Removing temporary folders...")
            shutil.rmtree(wheels_folder)
            shutil.rmtree(wheels_install_folder)

            self.log.info("Updating metadata file...")
            DependencyManager.create_cache_metadata(cache_metadata_file,
                                                    cache_zip_file,
                                                    packages)

        self.pkg = PythonPackageArchive(cache_file=cache_zip_file)

        exclude = os.path.normpath('/cache/') + os.path.sep
        self.pkg.add_modules(lambda f: (exclude in f),
                             *[m.replace('-', '_') for m in modules])

        # add config and policy
        self._add_functions_required_files(policy, queue_name)

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

        try:
            r = requests.get(status_url, timeout=30, verify=self.enable_ssl_cert)
        except requests.exceptions.ReadTimeout:
            self.log.error("Your Function app is not responding to a status request.")
            return False

        if r.status_code != 200:
            self.log.error("Application service returned an error.\n%s\n%s"
                           % (r.status_code, r.text))
            return False

        return True

    def publish(self, deployment_creds):
        self.close()

        # update perms of the package
        self._update_perms_package()
        zip_api_url = '%s/api/zipdeploy?isAsync=true' % deployment_creds.scm_uri

        self.log.info("Publishing Function package from %s" % self.pkg.path)

        zip_file = self.pkg.get_bytes()

        try:
            r = requests.post(zip_api_url, data=zip_file, timeout=300, verify=self.enable_ssl_cert)
        except requests.exceptions.ReadTimeout:
            self.log.error("Your Function App deployment timed out after 5 minutes. Try again.")

        r.raise_for_status()

        self.log.info("Function publish result: %s" % r.status_code)

    def close(self):
        self.pkg.close()
