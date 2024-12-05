# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
from collections import namedtuple

from ..azure_common import BaseTest, arm_template, cassette_name
from mock import patch

from c7n.exceptions import PolicyValidationError


class CostManagementExportTest(BaseTest):

    class MockExecutionHistory:
        def __init__(self, submitted_time_list):
            self.value = []
            MockExecutionItem = namedtuple('MockExecutionItem', ['submitted_time', 'serialize'])
            for t in submitted_time_list:
                self.value.append(MockExecutionItem(submitted_time=t, serialize=lambda b: ''))

    def test_schema_validate(self):
        self.assertTrue(self._get_policy(filters=[{'type': 'last-execution', 'age': 30}],
                                         actions=[{'type': 'execute'}],
                                         validate=True))

        with self.assertRaises(PolicyValidationError):
            self._get_policy(filters=[{'type': 'last-execution', 'age': -1}],
                             validate=True)

    @arm_template('cost-management-export.json')
    @cassette_name('common')
    def test_resource(self):
        p = self._get_policy()
        resources = p.run()
        self.assertEqual(len(resources), 1)

    # If we use 0 for 'age', we should get back same list of exports
    # 1. If it was executed right now, it still <= 0 days ago
    # 2. Exports with no executions are always included in the filter
    # This test is primarily to catch SDK changes regressions
    @arm_template('cost-management-export.json')
    @cassette_name('last-execution')
    def test_last_execution(self):
        p = self._get_policy(filters=[{'type': 'last-execution', 'age': 0}])
        resources = p.run()
        self.assertEqual(len(resources), 1)

    # There is no guarantee we have or don't have some real execution, so we will simulate possible
    # scenarios using patch
    @patch('azure.mgmt.costmanagement.operations.ExportsOperations.get_execution_history',
           return_value=MockExecutionHistory([datetime.datetime.now()]))
    @arm_template('cost-management-export.json')
    @cassette_name('common')
    def test_last_execution_mock(self, _1):
        p = self._get_policy(filters=[{'type': 'last-execution', 'age': 0}])
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @patch('azure.mgmt.costmanagement.operations.ExportsOperations.get_execution_history',
           return_value=MockExecutionHistory([datetime.datetime.now()]))
    @arm_template('cost-management-export.json')
    @cassette_name('common')
    def test_last_execution_mock_large_age(self, _1):
        p = self._get_policy(filters=[{'type': 'last-execution', 'age': 1}])
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @patch('azure.mgmt.costmanagement.operations.ExportsOperations.get_execution_history',
           return_value=MockExecutionHistory([]))
    @arm_template('cost-management-export.json')
    @cassette_name('common')
    def test_last_execution_mock_no_executions(self, _1):
        p = self._get_policy(filters=[{'type': 'last-execution', 'age': 1}])
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @patch('azure.mgmt.costmanagement.operations.ExportsOperations.execute')
    @arm_template('cost-management-export.json')
    @cassette_name('common')
    def test_execute(self, execute_mock):
        p = self._get_policy(actions=[{'type': 'execute'}])
        resources = p.run()
        self.assertEqual(len(resources), 1)

        execute_mock.assert_called_once()
        _, args, _ = execute_mock.mock_calls[0]
        self.assertTrue(args[0].startswith('subscriptions/'))
        self.assertEqual(args[1], 'cccostexport')

    def _get_policy(self, filters=[], actions=[], validate=False):
        return self.load_policy({
            'name': 'cost-management-export',
            'resource': 'azure.cost-management-export',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cccostexport'
                }
            ] + filters,
            'actions': actions
        }, validate=validate)
