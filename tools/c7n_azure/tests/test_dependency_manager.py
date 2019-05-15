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

import json
import os
import re
import shutil
import tempfile

from azure_common import BaseTest
from c7n_azure.dependency_manager import DependencyManager


class DependencyManagerTest(BaseTest):

    test_zip = os.path.join(os.path.dirname(__file__), 'data', 'test_cache', 'cache.zip')
    test_metadata = os.path.join(os.path.dirname(__file__), 'data', 'test_cache', 'metadata.json')

    test_zip_wrong = os.path.join(os.path.dirname(__file__), 'data', 'cache', 'wrong.zip')
    test_metadata_wrong = os.path.join(os.path.dirname(__file__), 'data', 'cache', 'wrong.json')

    test_packages = ['package1', 'package2']

    def test_get_file_hash(self):
        self.assertEqual(DependencyManager._get_file_hash(self.test_zip),
                         'EqAMFyrJXL+/+kEgji2hHQESjSHDTm4/SQZjwVdVcgg=')

    def test_get_string_hash(self):
        self.assertEqual(DependencyManager._get_string_hash(' '.join(self.test_packages)),
                         '1189b389ffc75d3a3174b6c63dee03fc')

    def test_create_cache_metadata(self):
        bench = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(bench))

        tmp_metadata = os.path.join(bench, 'metadata.json')
        DependencyManager.create_cache_metadata(tmp_metadata,
                                                self.test_zip,
                                                self.test_packages)

        with open(self.test_metadata, 'rt') as f:
            test_json = json.load(f)
        with open(tmp_metadata, 'rt') as f:
            tmp_json = json.load(f)
        self.assertTrue(test_json == tmp_json)

    def test_check_hash(self):
        self.assertFalse(DependencyManager.check_cache(self.test_metadata_wrong,
                                                       self.test_zip,
                                                       self.test_packages))
        self.assertFalse(DependencyManager.check_cache(self.test_metadata,
                                                       self.test_zip_wrong,
                                                       self.test_packages))
        self.assertFalse(DependencyManager.check_cache(self.test_metadata,
                                                       self.test_zip,
                                                       ['wrong', 'wrong2']))
        self.assertFalse(DependencyManager.check_cache(self.test_metadata,
                                                       self.test_metadata,
                                                       self.test_packages))

        self.assertTrue(DependencyManager.check_cache(self.test_metadata,
                                                      self.test_zip,
                                                      self.test_packages))

    def test_get_installed_distributions(self):
        d = DependencyManager.get_dependency_packages_list(['c7n-azure'], ['azure-cli-core'])
        self.assertTrue('azure-cli-core' not in d)
        self.assertTrue('adal' in d)
        self.assertEqual(sorted(d), d)
        # Remove versions from all packages & make sure there is no duplicates in the list
        regex = "^[^<>~=]*"
        d_no_versions = [re.match(regex, p).group(0) for p in d]
        self.assertEqual(len(d), len(set(d_no_versions)))
