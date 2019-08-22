# Copyright 2019 Microsoft Corporation
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

import logging

from azure_common import BaseTest, arm_template
from azure_common import cassette_name
from mock import mock

from c7n.exceptions import ResourceLimitExceeded


class QueryResourceManagerTest(BaseTest):

    @arm_template('emptyrg.json')
    @cassette_name('resource_limits')
    def test_policy_resource_limits(self):
        p = self.load_policy(
            {
                "name": "limits",
                "resource": "azure.resourcegroup",
                "max-resources-percent": 2.5,
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'eq',
                     'value': 'test_emptyrg'}]
            },
            validate=True)

        p.ctx.metrics.flush = mock.MagicMock()
        output = self.capture_logging('custodian.policy', level=logging.ERROR)
        self.assertRaises(ResourceLimitExceeded, p.run)
        self.assertTrue("policy:limits exceeded resource-limit:2.5% found:1 total:"
                        in output.getvalue())
        self.assertEqual(
            p.ctx.metrics.buf[0]['MetricName'], 'ResourceLimitExceeded')

    @arm_template('emptyrg.json')
    @cassette_name('resource_limits')
    def test_policy_resource_limits_count(self):
        p = self.load_policy(
            {
                "name": "limits",
                "resource": "azure.resourcegroup",
                "max-resources": 1,
            },
            validate=True)

        p.ctx.metrics.flush = mock.MagicMock()
        output = self.capture_logging('custodian.policy', level=logging.ERROR)
        self.assertRaises(ResourceLimitExceeded, p.run)
        self.assertTrue("policy:limits exceeded resource-limit:1 found:"
                        in output.getvalue())
        self.assertEqual(
            p.ctx.metrics.buf[0]['MetricName'], 'ResourceLimitExceeded')
