# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from .azure_common import BaseTest, arm_template
from .azure_common import cassette_name
from c7n_azure.session import Session
from unittest import mock
from unittest.mock import patch

from c7n.exceptions import ResourceLimitExceeded
from c7n.utils import local_session


class QueryResourceManagerTest(BaseTest):

    @arm_template('emptyrg.json')
    @cassette_name('resource_limits')
    def test_policy_resource_limits(self):
        p = self.load_policy(
            {
                "name": "limits",
                "resource": "azure.resourcegroup",
                "max-resources-percent": 0.01,
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
        self.assertTrue("policy:limits exceeded resource-limit:0.01% found:1 total:"
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

    @patch('c7n_azure.query.log.error')
    def test_query_filter_generic_exception(self, mock_log):
        with self.assertRaises(Exception):
            with patch('azure.mgmt.resource.resources.v%s.operations.'
                       'resource_groups_operations.ResourceGroupsOperations.list'
                       % QueryResourceManagerTest._get_resource_group_client_api_string()) \
                    as mock_list:
                mock_list.side_effect = Exception('test query exception')

                p = self.load_policy(
                    {
                        "name": "limits",
                        "resource": "azure.resourcegroup",
                    },
                    validate=True)

                p.run()

                mock_log.assert_called_once_with(
                    'Failed to query resource.'
                    '\nType: azure.resourcegroup.\nError: test query exception')

    @staticmethod
    def _get_resource_group_client_api_string():
        return local_session(Session) \
            .client('azure.mgmt.resource.ResourceManagementClient') \
            .DEFAULT_API_VERSION.replace("-", "_")
