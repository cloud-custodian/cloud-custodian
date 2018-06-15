from c7n.mu import PythonPackageArchive, custodian_archive
from c7n.utils import local_session
from c7n_azure.session import Session
import requests
import zipfile
import os
import shutil
import site
from sys import platform


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

    def _add_functions_required_files(self):
        self.pkg.add_directory(os.path.join(self.basedir, 'functionapp/HttpTrigger'))
        self.pkg.add_file(os.path.join(self.basedir, 'functionapp/.deployment'))
        self.pkg.add_file(os.path.join(self.basedir, 'functionapp/host.json'))
        self.pkg.add_file(os.path.join(self.basedir, 'functionapp/config.json'))

    def _add_cffi_module(self):
        # adding special modules
        self.pkg.add_modules('cffi')

        # Add native libraries that are missing
        site_pkg = site.getsitepackages()[0]

        # linux
        if platform == "linux" or platform == "linux2":
            self.pkg.add_file(os.path.join(site_pkg, '_cffi_backend.cpython-36m-x86_64-linux-gnu.so'))
            self.pkg.add_file(os.path.join(site_pkg, '.libs_cffi_backend/libffi-d78936b1.so.6.0.4'))
        # OS X
        elif platform == "darwin":
            # raise NotImplementedError('Cannot package Azure Function in Windows host OS.')
            self.pkg.add_file(os.path.join(site_pkg, '_cffi_backend.cpython-36m-darwin.so'))
        # Windows
        elif platform == "win32":
            raise NotImplementedError('Cannot package Azure Function in Windows host OS.')

    def build_azure_package(self):
        # Get dependencies for azure entry point
        modules, so_files = AzurePackageArchive._get_dependencies('c7n_azure/entry.py')

        # add all loaded modules
        modules.remove('azure')
        modules = modules.union({'c7n', 'c7n_azure', 'pkg_resources'})
        self.pkg.add_modules(*modules)

        # adding azure manually
        # we need to ignore the __init__.py of the azure namespace for packaging
        # https://www.python.org/dev/peps/pep-0420/
        self.pkg.add_modules('azure', ignore=lambda f: f == 'azure/__init__.py')

        # add Functions HttpTrigger
        self._add_functions_required_files()

        # cffi module needs special handling
        self._add_cffi_module()

        self.pkg.close()


def publish(app_name, pkg):
    s = local_session(Session)
    zip_api_url = 'https://%s.scm.azurewebsites.net/api/zipdeploy?isAsync=true' % (app_name)
    bearer_token = 'Bearer %s' % (s.credentials._token_retriever()[1])
    headers = {
        'Content-type': 'application/zip',
        'Authorization': bearer_token
    }

    zip_file = open(pkg.path, 'rb').read()
    r = requests.post(zip_api_url, headers=headers, data=zip_file)


if __name__ == "__main__":
    archive = AzurePackageArchive()
    archive.build_azure_package()

    # Unzip the archive for testing
    test_app_path = os.path.join(archive.basedir, 'test_app2')
    if os.path.exists(test_app_path):
        shutil.rmtree(test_app_path)
        os.makedirs(test_app_path)

    shutil.copy(archive.pkg.path, os.path.join(os.path.dirname(test_app_path), 'test_app.zip'))
    zip = zipfile.ZipFile(archive.pkg.path, 'r')
    zip.extractall(test_app_path)
