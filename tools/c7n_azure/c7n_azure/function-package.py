import os
import shutil
import sys
import tempfile
import json

import requests
from c7n_azure.session import Session

from c7n.mu import PythonPackageArchive
from c7n.utils import local_session


class FunctionPackage(object):

    def __init__(self):
        self.basedir = os.path.dirname(os.path.realpath(__file__))
        self.pkg = PythonPackageArchive()

    def _add_functions_required_files(self, policy):
        policy_name = policy['name']

        self.pkg.add_file(os.path.join(self.basedir, 'function.py'),
                          dest=policy_name + '/function.py')

        self.pkg.add_contents(dest=policy_name + '/__init__.py', contents='')

        self._add_host_config()
        self._add_function_config(policy)
        self._add_policy(policy)

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

    def _add_function_config(self, policy):
        config = \
            {
              "scriptFile": "function.py",
              "bindings": [
                {
                  "authLevel": "anonymous",
                  "type": "httpTrigger",
                  "direction": "in",
                  "name": "req"
                },
                {
                  "type": "http",
                  "direction": "out",
                  "name": "$return"
                }
              ]
            }

        self.pkg.add_contents(dest=policy['name'] + '/function.json', contents=json.dumps(config))

    def _add_policy(self, policy):
        self.pkg.add_contents(dest=policy['name'] + '/config.json', contents=json.dumps(policy))

    def _add_cffi_module(self):
        # adding special modules
        self.pkg.add_modules('cffi')

        # Add native libraries that are missing
        site_pkg = FunctionPackage.get_site_packages()[0]

        # linux
        platform = sys.platform
        if platform == "linux" or platform == "linux2":
            self.pkg.add_file(os.path.join(site_pkg, '_cffi_backend.cpython-36m-x86_64-linux-gnu.so'))
            self.pkg.add_file(os.path.join(site_pkg, '.libs_cffi_backend/libffi-d78936b1.so.6.0.4'),
                              '.libs_cffi_backend/libffi-d78936b1.so.6.0.4')
        # MacOS
        elif platform == "darwin":
            raise NotImplementedError('Cannot package Azure Function in MacOS host OS, please use linux.')
        # Windows
        elif platform == "win32":
            raise NotImplementedError('Cannot package Azure Function in Windows host OS, please use linux or WSL.')

    def _update_perms_package(self):
        os.chmod(self.pkg.path, 0o0644)

    def build_azure_package(self, policy):
        # Get dependencies for azure entry point
        modules, so_files = FunctionPackage._get_dependencies('c7n_azure/entry.py')

        # add all loaded modules
        modules.remove('azure')
        modules = modules.union({'c7n', 'c7n_azure', 'pkg_resources'})
        self.pkg.add_modules(None, *modules)

        # adding azure manually
        # we need to ignore the __init__.py of the azure namespace for packaging
        # https://www.python.org/dev/peps/pep-0420/
        self.pkg.add_modules(lambda f: f == 'azure/__init__.py', 'azure')

        # add Functions HttpTrigger
        self._add_functions_required_files(policy)

        # generate and add auth
        s = local_session(Session)
        self.pkg.add_contents(dest=policy['name'] + '/auth.json', contents=s.get_auth_string())

        # cffi module needs special handling
        self._add_cffi_module()

        self.pkg.close()

        # update perms of the package
        self._update_perms_package()

    def close(self):
        self.pkg.close()

    @staticmethod
    def publish(app_name, pkg):
        s = local_session(Session)
        zip_api_url = 'https://%s.scm.azurewebsites.net/api/zipdeploy?isAsync=true' % (app_name)
        headers = {
            'Content-type': 'application/zip',
            'Authorization': 'Bearer %s' % (s.get_bearer_token())
        }

        zip_file = open(pkg.path, 'rb').read()
        r = requests.post(zip_api_url, headers=headers, data=zip_file)
        print(r)

    @staticmethod
    def get_site_packages():
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
                             if v.__file__ is not None and "site-packages" in v.__file__
                             and ".so" in v.__file__]))

        return set(modules), so_files


# ex: python create_function_zip.py /home/test_app linuxcontainer1 policy_name
if __name__ == "__main__":
    archive = FunctionPackage()
    archive.build_azure_package(sys.argv[3])

    # Unzip the archive for testing
    test_app_path = sys.argv[1]
    if os.path.exists(test_app_path):
        shutil.rmtree(test_app_path)
        os.makedirs(test_app_path)

    shutil.copy(archive.pkg.path, os.path.join(os.path.dirname(test_app_path), 'archive.zip'))

    # debug extract
    archive.pkg.get_reader().extractall(test_app_path)

    FunctionPackage.publish(sys.argv[2], archive.pkg)
