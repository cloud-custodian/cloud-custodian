# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import os
import time
import zipfile

from azure.mgmt.web.models import User
from c7n_azure.constants import ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION, \
    FUNCTION_TIME_TRIGGER_MODE, FUNCTION_EVENT_TRIGGER_MODE
from c7n_azure.function_package import FunctionPackage, AzurePythonPackageArchive
from unittest.mock import patch, MagicMock

from .azure_common import BaseTest

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

    def test_auth_file_system_assigned(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'provision-options': {
                     'identity': {
                         'id': 'awolf',
                         'client_id': 'dog',
                         'type': 'UserAssigned'}},
                 'events': ['PublicIpWrite']}}, validate=False)
        packer = FunctionPackage(p.data['name'])
        packer.pkg = AzurePythonPackageArchive()
        packer._add_functions_required_files(p.data, 'c7n-azure==1.0', 'test-queue')

        packer.pkg.close()
        with zipfile.ZipFile(packer.pkg.path) as zf:
            content = json.loads(zf.read('test-azure-public-ip/auth.json'))
            self.assertEqual(content, {
                'client_id': 'dog',
                'subscription_id': None,
                'use_msi': True,
                'tenant_id': self.session.get_tenant_id()})

    def test_auth_file_user_assigned_identity(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'provision-options': {
                     'identity': {
                         'type': 'SystemAssigned'}},
                 'events': ['PublicIpWrite']}})
        packer = FunctionPackage(p.data['name'])
        packer.pkg = AzurePythonPackageArchive()
        packer._add_functions_required_files(p.data, 'c7n-azure==1.0', 'test-queue')

        packer.pkg.close()
        with zipfile.ZipFile(packer.pkg.path) as zf:
            content = json.loads(zf.read('test-azure-public-ip/auth.json'))
            self.assertEqual(content, {
                'subscription_id': None,
                'use_msi': True,
                'tenant_id': self.session.get_tenant_id()})

    def test_add_function_config_events(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['PublicIpWrite']},
        })

        packer = FunctionPackage(p.data['name'])

        config = packer.get_function_config(p.data)

        binding = json.loads(config)

        self.assertEqual(binding['bindings'][0]['type'], 'queueTrigger')
        self.assertEqual(binding['bindings'][0]['connection'], 'AzureWebJobsStorage')

    def test_zipped_files_have_modified_timestamp(self):
        t = time.gmtime(1577854800)
        package = AzurePythonPackageArchive()
        package.package_time = t
        package.add_contents('test.txt', 'Hello, World')
        package.close()

        zinfo = package._zip_file.infolist()[0]
        self.assertEqual('test.txt', zinfo.filename)
        self.assertEqual(t[0:6], zinfo.date_time)

    @patch("c7n_azure.session.Session.get_functions_auth_string", return_value="")
    def test_event_package_files(self, session_mock):
        p = self.load_policy({
            'name': 'test-azure-package',
            'resource': 'azure.resourcegroup',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['ResourceGroupWrite']},
        })

        packer = FunctionPackage(p.data['name'])
        packer.pkg = AzurePythonPackageArchive()

        packer._add_functions_required_files(p.data, 'c7n-azure==1.0', 'test-queue')
        files = packer.pkg._zip_file.filelist

        self.assertTrue(FunctionPackageTest._file_exists(files, 'test-azure-package/function.py'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'test-azure-package/__init__.py'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'test-azure-package/function.json'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'test-azure-package/config.json'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'host.json'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'requirements.txt'))

    @patch("c7n_azure.session.Session.get_functions_auth_string", return_value="")
    def test_no_policy_add_required_files(self, session_mock):
        """ Tools such as mailer will package with no policy """

        packer = FunctionPackage('name')
        packer.pkg = AzurePythonPackageArchive()

        packer._add_functions_required_files(None, 'c7n-azure==1.0')
        files = packer.pkg._zip_file.filelist

        self.assertTrue(FunctionPackageTest._file_exists(files, 'host.json'))
        self.assertTrue(FunctionPackageTest._file_exists(files, 'requirements.txt'))

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
                         'https://uri/api/zipdeploy?isAsync=true&synctriggers=true')
        self.assertEqual(post_mock.call_args[1]['headers']['content-type'],
                         'application/octet-stream')

    def test_env_var_disables_cert_validation(self):
        p = self.load_policy({
            'name': 'test-azure-package',
            'resource': 'azure.resourcegroup',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['ResourceGroupWrite']},
        })

        with patch.dict(os.environ,
                        {
                            ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION: 'YES'
                        }, clear=True):
            packer = FunctionPackage(p.data['name'])
            self.assertFalse(packer.enable_ssl_cert)

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
