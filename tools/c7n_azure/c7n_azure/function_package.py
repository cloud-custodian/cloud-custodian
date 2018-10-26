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
import fnmatch
import json
import logging
import os
import sys
import time

import requests
from c7n_azure.constants import ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION, \
    FUNCTION_EVENT_TRIGGER_MODE, FUNCTION_TIME_TRIGGER_MODE

from c7n_azure.session import Session

from c7n.mu import PythonPackageArchive
from c7n.utils import local_session


class FunctionPackage(object):

    def __init__(self, name, function_path=None):
        self.log = logging.getLogger('custodian.azure.function_package')
        self.pkg = PythonPackageArchive()
        self.name = name
        self.function_path = function_path or os.path.join(
            os.path.dirname(os.path.realpath(__file__)), 'function.py')
        self.enable_ssl_cert = not distutils.util.strtobool(
            os.environ.get(ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION, 'no'))

        if not self.enable_ssl_cert:
            self.log.warning('SSL Certificate Validation is disabled')

    def _add_functions_required_files(self, policy, queue_name=None):
        self.pkg.add_file(self.function_path,
                          dest=self.name + '/function.py')

        self.pkg.add_contents(dest=self.name + '/__init__.py', contents='')

        self._add_host_config()

        if policy:
            config_contents = self.get_function_config(policy, queue_name)
            policy_contents = self._get_policy(policy)
            self.pkg.add_contents(dest=self.name + '/function.json',
                                  contents=config_contents)

            self.pkg.add_contents(dest=self.name + '/config.json',
                                  contents=policy_contents)

            if policy['mode']['type'] == FUNCTION_EVENT_TRIGGER_MODE:
                self._add_queue_binding_extensions()

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

    def _add_cffi_module(self):
        """CFFI native bits aren't discovered automatically
        so for now we grab them manually from supported platforms"""

        self.pkg.add_modules('cffi')

        # Add native libraries that are missing
        site_pkg = FunctionPackage._get_site_packages()[0]

        # linux
        platform = sys.platform
        if platform == "linux" or platform == "linux2":
            for so_file in os.listdir(site_pkg):
                if fnmatch.fnmatch(so_file, '*ffi*.so*'):
                    self.pkg.add_file(os.path.join(site_pkg, so_file))

            self.pkg.add_directory(os.path.join(site_pkg, '.libs_cffi_backend'))

        # MacOS
        elif platform == "darwin":
            raise NotImplementedError('Cannot package Azure Function in MacOS host OS, '
                                      'please use linux.')
        # Windows
        elif platform == "win32":
            raise NotImplementedError('Cannot package Azure Function in Windows host OS, '
                                      'please use linux or WSL.')

    def _update_perms_package(self):
        os.chmod(self.pkg.path, 0o0644)

    def build(self, policy, queue_name=None, entry_point=None, extra_modules=None):
        # Get dependencies for azure entry point
        entry_point = entry_point or \
            os.path.join(os.path.dirname(os.path.realpath(__file__)), 'entry.py')
        modules, so_files = FunctionPackage._get_dependencies(entry_point)

        # add all loaded modules
        modules.discard('azure')
        modules = modules.union({'c7n', 'c7n_azure', 'pkg_resources',
                                 'knack', 'argcomplete', 'applicationinsights'})
        if extra_modules:
            modules = modules.union(extra_modules)

        self.pkg.add_modules(None, *modules)

        # adding azure manually
        # we need to ignore the __init__.py of the azure namespace for packaging
        # https://www.python.org/dev/peps/pep-0420/
        self.pkg.add_modules(lambda f: f == 'azure/__init__.py', 'azure')

        # add config and policy
        self._add_functions_required_files(policy, queue_name)

        # generate and add auth
        s = local_session(Session)
        self.pkg.add_contents(dest=self.name + '/auth.json', contents=s.get_functions_auth_string())

        # cffi module needs special handling
        self._add_cffi_module()

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

        zip_file = open(self.pkg.path, 'rb').read()

        try:
            r = requests.post(zip_api_url, data=zip_file, timeout=300, verify=self.enable_ssl_cert)
        except requests.exceptions.ReadTimeout:
            self.log.error("Your Function App deployment timed out after 5 minutes. Try again.")

        r.raise_for_status()

        self.log.info("Function publish result: %s" % r.status_code)

    def close(self):
        self.pkg.close()

    @staticmethod
    def _get_site_packages():
        """Returns a list containing all global site-packages directories
        (and possibly site-python).
        For each directory present in the global ``PREFIXES``, this function
        will find its `site-packages` subdirectory depending on the system
        environment, and will return a list of full paths.
        """
        site_packages = []
        seen = set()
        prefixes = [sys.prefix, sys.exec_prefix]

        for prefix in prefixes:
            if not prefix or prefix in seen:
                continue
            seen.add(prefix)

            if sys.platform in ('os2emx', 'riscos'):
                site_packages.append(os.path.join(prefix, "Lib", "site-packages"))
            elif os.sep == '/':
                site_packages.append(os.path.join(prefix, "lib",
                                                  "python" + sys.version[:3],
                                                  "site-packages"))
                site_packages.append(os.path.join(prefix, "lib", "site-python"))
            else:
                site_packages.append(prefix)
                site_packages.append(os.path.join(prefix, "lib", "site-packages"))
        return site_packages

    @staticmethod
    def _get_dependencies(entry_point):
        # Dynamically find all imported modules
        from modulefinder import ModuleFinder
        finder = ModuleFinder()
        finder.run_script(entry_point)
        imports = list(set([v.__file__.split('site-packages/', 1)[-1].split('/')[0]
                            for (k, v) in finder.modules.items()
                            if v.__file__ is not None and "site-packages" in v.__file__]))

        # Get just the modules, ignore the so and py now (maybe useful for calls to add_file)
        modules = [i.split('.py')[0] for i in imports if ".so" not in i]

        so_files = list(set([v.__file__
                             for (k, v) in finder.modules.items()
                             if v.__file__ is not None and "site-packages" in
                             v.__file__ and ".so" in v.__file__]))

        return set(modules), so_files
