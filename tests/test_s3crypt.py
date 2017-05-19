# Copyright 2016 Capital One Services, LLC
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
import tempfile

from unittest import TestCase
from c7n.ufuncs import s3crypt


class TestS3Crypt(TestCase):

    def setUp(self):
        self.old_dir = os.getcwd()
        os.chdir(tempfile.gettempdir())
        self.config_data = {
            'test': 'data',
            'large': False,
        }
        with open('config.json', 'w') as conf:
            json.dump(self.config_data, conf)

    def tearDown(self):
        os.remove('config.json')
        os.chdir(self.old_dir)

    def test_init(self):
        s3crypt.init()
        self.assertEqual(s3crypt.config, self.config_data)

        # Run a second time to ensure it is idempotent
        s3crypt.init()
        self.assertEqual(s3crypt.config, self.config_data)
