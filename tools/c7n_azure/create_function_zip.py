import os
import shutil
import sys
import tempfile

import requests
from c7n_azure.session import Session

from c7n.mu import PythonPackageArchive
from c7n.utils import local_session


class AzurePackageArchive(object):

    def __init__(self):
        self.basedir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'function')
        self.pkg = PythonPackageArchive()

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

    def _add_functions_required_files(self, policy_name):
        self.pkg.add_file(os.path.join(self.basedir, 'functionapp/HttpTrigger/__init__.py'),
                          dest=policy_name + '/__init__.py')
        self.pkg.add_file(os.path.join(self.basedir, 'functionapp/HttpTrigger/main.py'),
                          dest=policy_name + '/main.py')
        self.pkg.add_file(os.path.join(self.basedir, 'functionapp/host.json'))
        self.pkg.add_file(os.path.join(self.basedir, 'functionapp/HttpTrigger/function.json'),
                          dest=policy_name + '/function.json')
        self.pkg.add_file(os.path.join(self.basedir, 'functionapp/HttpTrigger/config.json'),
                          dest=policy_name + '/config.json')

    def _add_cffi_module(self):
        # adding special modules
        self.pkg.add_modules('cffi')

        # Add native libraries that are missing
        site_pkg = getsitepackages()[0]

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

    def build_azure_package(self, policy_name):
        # Get dependencies for azure entry point
        modules, so_files = AzurePackageArchive._get_dependencies('c7n_azure/entry.py')

        # add all loaded modules
        modules.remove('azure')
        modules = modules.union({'c7n', 'c7n_azure', 'pkg_resources'})
        self.pkg.add_modules(None, *modules)

        # adding azure manually
        # we need to ignore the __init__.py of the azure namespace for packaging
        # https://www.python.org/dev/peps/pep-0420/
        self.pkg.add_modules(lambda f: f == 'azure/__init__.py', 'azure')

        # add Functions HttpTrigger
        self._add_functions_required_files(policy_name)

        # generate and add auth file
        s = local_session(Session)

        with tempfile.NamedTemporaryFile() as auth:
            s.write_auth_file(auth.name)
            self.pkg.add_file(auth.name, dest=policy_name + '/auth.json')

        # cffi module needs special handling
        self._add_cffi_module()

        self.pkg.close()

        # update perms of the package
        self._update_perms_package()

    def close(self):
        self.pkg.close()


def publish(app_name, pkg):
    s = local_session(Session)
    zip_api_url = 'https://%s.scm.azurewebsites.net/api/zipdeploy?isAsync=true' % (app_name)
    bearer_token = 'Bearer %s' % (s.get_bearer_token())
    headers = {
        'Content-type': 'application/zip',
        'Authorization': bearer_token
    }

    zip_file = open(pkg.path, 'rb').read()
    r = requests.post(zip_api_url, headers=headers, data=zip_file)
    print(r)

def getsitepackages():
    """Returns a list containing all global site-packages directories
    (and possibly site-python).
    For each directory present in the global ``PREFIXES``, this function
    will find its `site-packages` subdirectory depending on the system
    environment, and will return a list of full paths.
    """
    sitepackages = []
    seen = set()
    prefixes = [sys.prefix, sys.exec_prefix]

    for prefix in prefixes:
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)

        if sys.platform in ('os2emx', 'riscos'):
            sitepackages.append(os.path.join(prefix, "Lib", "site-packages"))
        elif os.sep == '/':
            sitepackages.append(os.path.join(prefix, "lib",
                                             "python" + sys.version[:3],
                                             "site-packages"))
            sitepackages.append(os.path.join(prefix, "lib", "site-python"))
        else:
            sitepackages.append(prefix)
            sitepackages.append(os.path.join(prefix, "lib", "site-packages"))
    return sitepackages


# ex: python create_function_zip.py /home/test_app linuxcontainer1 policy_name
if __name__ == "__main__":
    archive = AzurePackageArchive()
    archive.build_azure_package(sys.argv[3])
    archive.close()

    # Unzip the archive for testing
    test_app_path = sys.argv[1]
    if os.path.exists(test_app_path):
        shutil.rmtree(test_app_path)
        os.makedirs(test_app_path)

    shutil.copy(archive.pkg.path, os.path.join(os.path.dirname(test_app_path), 'archive.zip'))

    # debug extract
    archive.pkg.get_reader().extractall(test_app_path)

    publish(sys.argv[2], archive.pkg)
