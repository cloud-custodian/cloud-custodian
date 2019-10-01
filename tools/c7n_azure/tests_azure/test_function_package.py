# Copyright 2015-2018 Capital One Services, LLC
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
import time

from .azure_common import BaseTest
from c7n_azure.function_package import FunctionPackage, AzurePythonPackageArchive
from c7n_azure.constants import ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION, \
    FUNCTION_TIME_TRIGGER_MODE, FUNCTION_EVENT_TRIGGER_MODE
from mock import patch, MagicMock, PropertyMock

from azure.mgmt.web.models import User

test_files_folder = os.path.join(os.path.dirname(__file__), 'data')


class FunctionPackageTest(BaseTest):

    def setUp(self):
        super(FunctionPackageTest, self).setUp()

    def test_add_function_config_periodic(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'mode':
                {'type': FUNCTION_TIME_TRIGGER_MODE,
                 'schedule': '0 1 0 1 1 1'}
        })

        packer = FunctionPackage(p.data['name'])

        config = packer.get_function_config(p.data)

        binding = json.loads(config)

        self.assertEqual(binding['bindings'][0]['type'], 'timerTrigger')
        self.assertEqual(binding['bindings'][0]['name'], 'input')
        self.assertEqual(binding['bindings'][0]['schedule'], '0 1 0 1 1 1')

    def test_add_function_config_events(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']},
        })

        packer = FunctionPackage(p.data['name'])

        config = packer.get_function_config(p.data)

        binding = json.loads(config)

        self.assertEqual(binding['bindings'][0]['type'], 'queueTrigger')
        self.assertEqual(binding['bindings'][0]['connection'], 'AzureWebJobsStorage')

    def test_add_policy(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']},
        })

        packer = FunctionPackage(p.data['name'])

        policy = json.loads(packer._get_policy(p.data))

        self.assertEqual(policy['policies'][0],
                         {u'resource': u'azure.publicip',
                          u'name': u'test-azure-public-ip',
                          u'mode': {u'type': u'azure-event-grid',
                                    u'events': [u'VmWrite']}})

    def test_zipped_files_have_modified_timestamp(self):
        t = time.gmtime(1577854800)
        package = AzurePythonPackageArchive()
        package.package_time = t
        package.add_contents('test.txt', 'Hello, World')
        package.close()

        zinfo = package._zip_file.infolist()[0]
        self.assertEqual('test.txt', zinfo.filename)
        self.assertEqual(t[0:6], zinfo.date_time)

    def test_zipped_files_with_zip_cache_unmodified_cache_timestamps(self):
        cache_ts = time.gmtime(1577000000)
        cache = AzurePythonPackageArchive()
        cache.package_time = cache_ts
        cache.add_contents('cache.txt', 'I am a cache file')
        cache.close()

        new_ts = time.gmtime(1577854800)
        package = AzurePythonPackageArchive(cache_file=cache.path)
        package.package_time = new_ts
        package.add_contents('new.txt', 'I am a new file')
        package.close()

        cache_file = package._zip_file.infolist()[0]
        self.assertEqual('cache.txt', cache_file.filename)
        self.assertEqual(cache_ts[0:6], cache_file.date_time)

        new_file = package._zip_file.infolist()[1]
        self.assertEqual('new.txt', new_file.filename)
        self.assertEqual(new_ts[0:6], new_file.date_time)

    @patch("c7n_azure.session.Session.get_functions_auth_string", return_value="")
    def test_event_package_files(self, session_mock):
        p = self.load_policy({
            'name': 'test-azure-package',
            'resource': 'azure.resourcegroup',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']},
        })

        packer = FunctionPackage(p.data['name'])
        packer.pkg = AzurePythonPackageArchive()

        packer._add_functions_required_files(p.data, 'test-queue')
        files = packer.pkg._zip_file.filelist

        self.assertTrue(FunctionPackageTest._file_exists(files, 'test-azure-package/function.py'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'test-azure-package/__init__.py'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'test-azure-package/function.json'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'test-azure-package/config.json'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'host.json'))

    @patch("c7n_azure.session.Session.get_functions_auth_string", return_value="")
    def test_no_policy_add_required_files(self, session_mock):
        """ Tools such as mailer will package with no policy """

        packer = FunctionPackage('name')
        packer.pkg = AzurePythonPackageArchive()

        packer._add_functions_required_files(None)
        files = packer.pkg._zip_file.filelist

        self.assertTrue(FunctionPackageTest._file_exists(files, 'host.json'))

    def test_add_host_config(self):
        packer = FunctionPackage('test')
        packer.pkg = AzurePythonPackageArchive()
        with patch('c7n_azure.function_package.AzurePythonPackageArchive.add_contents') as mock:
            packer._add_host_config(FUNCTION_EVENT_TRIGGER_MODE)
            mock.assert_called_once()
            self.assertEqual(mock.call_args[1]['dest'], 'host.json')
            self.assertTrue('extensionBundle' in json.loads(mock.call_args[1]['contents']))

        with patch('c7n_azure.function_package.AzurePythonPackageArchive.add_contents') as mock:
            packer._add_host_config(FUNCTION_TIME_TRIGGER_MODE)
            mock.assert_called_once()
            self.assertEqual(mock.call_args[1]['dest'], 'host.json')
            self.assertFalse('extensionBundle' in json.loads(mock.call_args[1]['contents']))

    @patch('requests.post')
    def test_publish(self, post_mock):
        status_mock = MagicMock()
        post_mock.return_value = status_mock
        packer = FunctionPackage('test')
        packer.pkg = AzurePythonPackageArchive()
        creds = User(publishing_user_name='user',
                     publishing_password='password',
                     scm_uri='https://uri')

        packer.publish(creds)

        post_mock.assert_called_once()
        status_mock.raise_for_status.assert_called_once()

        self.assertEqual(post_mock.call_args[0][0],
                         'https://uri/api/zipdeploy?isAsync=true')
        self.assertEqual(post_mock.call_args[1]['headers']['content-type'],
                         'application/octet-stream')

    def test_env_var_disables_cert_validation(self):
        p = self.load_policy({
            'name': 'test-azure-package',
            'resource': 'azure.resourcegroup',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']},
        })

        with patch.dict(os.environ,
                        {
                            ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION: 'YES'
                        }, clear=True):
            packer = FunctionPackage(p.data['name'])
            self.assertFalse(packer.enable_ssl_cert)

    @patch('c7n_azure.function_package.FunctionPackage._add_functions_required_files')
    @patch('shutil.rmtree')
    def test_package_build_no_cache(self, rmtree_mock, add_files_mock):
        functions = [('check_cache', False),
                     ('prepare_non_binary_wheels', None),
                     ('download_wheels', None),
                     ('install_wheels', None),
                     ('create_cache_metadata', None)]
        mocks = []
        for f in functions:
            mocks.append(self._create_patch(
                'c7n_azure.dependency_manager.DependencyManager.' + f[0],
                return_value=f[1]))
        add_modules_mock = self._create_patch(
            'c7n_azure.function_package.AzurePythonPackageArchive.add_modules')
        mocks.append(self._create_patch(
            'c7n_azure.function_package.AzurePythonPackageArchive.add_file'))

        cache_zip = os.path.join(test_files_folder, 'cache.zip')
        self.addCleanup(os.remove, cache_zip)

        packer = FunctionPackage('test', cache_override_path=test_files_folder)
        packer.build({}, [], [], [], 'queue')

        for m in mocks:
            m.assert_called_once()

        add_files_mock.assert_called_once()

        self.assertEqual(rmtree_mock.call_count, 3)
        self.assertEqual(add_modules_mock.call_count, 3)
        self.assertTrue(os.path.exists(cache_zip))

    @patch('c7n_azure.function_package.FunctionPackage._add_functions_required_files')
    @patch('shutil.rmtree')
    @patch('c7n_azure.function_package.FunctionPackage.cache_folder',
           new_callable=PropertyMock,
           return_value=test_files_folder)
    def test_package_build_cache(self, _1, rmtree_mock, add_files_mock):
        cache_zip = os.path.join(test_files_folder, 'cache.zip')

        self._create_patch('c7n_azure.dependency_manager.DependencyManager.check_cache',
                           return_value=True)

        functions = [('prepare_non_binary_wheels', None),
                     ('download_wheels', None),
                     ('install_wheels', None),
                     ('create_cache_metadata', None)]
        mocks = []
        for f in functions:
            mocks.append(self._create_patch(
                'c7n_azure.dependency_manager.DependencyManager.' + f[0],
                return_value=f[1]))
        add_modules_mock = self._create_patch(
            'c7n_azure.function_package.AzurePythonPackageArchive.add_modules')
        self._create_patch('c7n_azure.function_package.AzurePythonPackageArchive.__init__')

        packer = FunctionPackage('test')
        packer.build({}, [], [], [], 'queue')

        for m in mocks:
            self.assertEqual(m.call_count, 0)

        add_files_mock.assert_called_once()

        self.assertEqual(rmtree_mock.call_count, 0)
        self.assertEqual(add_modules_mock.call_count, 1)
        self.assertFalse(os.path.exists(cache_zip))

    def def_cert_validation_on_by_default(self):
        p = self.load_policy({
            'name': 'test-azure-package',
            'resource': 'azure.resourcegroup',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']},
        })

        packer = FunctionPackage(p.data['name'])
        self.assertTrue(packer.enable_ssl_cert)

    def _create_patch(self, name, return_value=None):
        patcher = patch(name, return_value=return_value)
        p = patcher.start()
        self.addCleanup(patcher.stop)
        return p

    @staticmethod
    def _file_exists(files, name):
        file_exists = [True for item in files if item.filename == name][0]
        return file_exists or False
