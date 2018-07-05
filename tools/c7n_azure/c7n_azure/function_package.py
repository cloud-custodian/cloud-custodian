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

import fnmatch
import json
import logging
import os
import sys

import requests
from c7n_azure.session import Session

from c7n.mu import PythonPackageArchive
from c7n.utils import local_session


class FunctionPackage(object):

    def __init__(self, policy):
        self.log = logging.getLogger('custodian.azure.function_package')
        self.basedir = os.path.dirname(os.path.realpath(__file__))
        self.pkg = PythonPackageArchive()
        self.policy = policy

    def _add_functions_required_files(self):
        policy_name = self.policy['name']

        self.pkg.add_file(os.path.join(self.basedir, 'function.py'),
                          dest=policy_name + '/function.py')

        self.pkg.add_contents(dest=policy_name + '/__init__.py', contents='')

        self._add_host_config()
        self._add_function_config()
        self._add_policy()

    def _add_host_config(self):
        config = \
            {
                "http": {
                    "routePrefix": "api",
                    "maxConcurrentRequests": 5,
                    "maxOutstandingRequests": 30
                },
                "logger": {
                    "defaultLevel": "Trace",
                    "categoryLevels": {
                        "Worker": "Trace"
                    }
                },
                "queues": {
                    "visibilityTimeout": "00:00:10"
                },
                "swagger": {
                    "enabled": True
                },
                "eventHub": {
                    "maxBatchSize": 1000,
                    "prefetchCount": 1000,
                    "batchCheckpointFrequency": 1
                },
                "healthMonitor": {
                    "enabled": True,
                    "healthCheckInterval": "00:00:10",
                    "healthCheckWindow": "00:02:00",
                    "healthCheckThreshold": 6,
                    "counterThreshold": 0.80
                },
                "functionTimeout": "00:05:00"
            }
        self.pkg.add_contents(dest='host.json', contents=json.dumps(config))

    def _add_function_config(self):
        config = \
            {
                "scriptFile": "function.py",
                "bindings": [{
                    "direction": "in"
                }]
            }

        mode_type = self.policy['mode']['type']
        binding = config['bindings'][0]

        if mode_type == 'azure-periodic':
            binding['type'] = 'timerTrigger'
            binding['name'] = 'input'
            binding['schedule'] = self.policy['mode']['schedule']

        elif mode_type == 'azure-stream':
            binding['type'] = 'eventHubTrigger'
            binding['name'] = 'input'
            binding['eventHubName'] = 'eventHubName'
            binding['consumerGroup'] = 'consumerGroup'
            binding['connection'] = 'name_of_app_setting_with_read_conn_string'

        else:
            self.log.error("Mode not yet supported for Azure functions (%s)"
                           % mode_type)

        self.pkg.add_contents(dest=self.policy['name'] + '/function.json',
                              contents=json.dumps(config))

    def _add_policy(self):
        self.pkg.add_contents(dest=self.policy['name'] + '/config.json',
                              contents=json.dumps(self.policy))

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

    def build(self):
        # Get dependencies for azure entry point
        modules, so_files = FunctionPackage._get_dependencies('entry.py')

        # add all loaded modules
        modules.remove('azure')
        modules = modules.union({'c7n', 'c7n_azure', 'pkg_resources'})
        self.pkg.add_modules(None, *modules)

        # adding azure manually
        # we need to ignore the __init__.py of the azure namespace for packaging
        # https://www.python.org/dev/peps/pep-0420/
        self.pkg.add_modules(lambda f: f == 'azure/__init__.py', 'azure')

        # add Functions HttpTrigger
        self._add_functions_required_files()

        # generate and add auth
        s = local_session(Session)
        self.pkg.add_contents(dest=self.policy['name'] + '/auth.json', contents=s.get_auth_string())

        # cffi module needs special handling
        self._add_cffi_module()

        self.pkg.close()

        # update perms of the package
        self._update_perms_package()

    def publish(self, app_name):
        s = local_session(Session)
        zip_api_url = 'https://%s.scm.azurewebsites.net/api/zipdeploy?isAsync=true' % (app_name)
        headers = {
            'Content-type': 'application/zip',
            'Authorization': 'Bearer %s' % (s.get_bearer_token())
        }

        self.log.info("Publishing package at: %s" % self.pkg.path)

        zip_file = open(self.pkg.path, 'rb').read()
        r = requests.post(zip_api_url, headers=headers, data=zip_file)

        self.log.info("Function publish result: %s %s" % (r, r.text))

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
        finder.run_script(os.path.join(os.path.dirname(os.path.realpath(__file__)), entry_point))
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
