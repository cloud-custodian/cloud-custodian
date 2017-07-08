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

import argparse

from .common import BaseTest
from c7n.commands import validate as validate_yaml_policies


class CommandsValidateTest(BaseTest):

    def test_failed_validation(self):
        yaml_validate_options = argparse.Namespace(
            command = 'c7n.commands.validate',
            config  = None,
            configs = [
                'tests/data/test_policies/ebs-BADVALIDATION.yml',
                'tests/data/test_policies/ami-GOODVALIDATION.yml'
            ],
            debug=False,
            subparser='validate',
            verbose=False
        )
        with self.assertRaises(SystemExit) as exit:
            validate_yaml_policies(yaml_validate_options)
        # if there is a bad policy in the batch being validated, there should be an exit 1
        self.assertEqual(exit.exception.code, 1)
        yaml_validate_options.configs.remove('tests/data/test_policies/ebs-BADVALIDATION.yml')
        # if there are only good policy, it should exit none
        self.assertIsNone(validate_yaml_policies(yaml_validate_options))
