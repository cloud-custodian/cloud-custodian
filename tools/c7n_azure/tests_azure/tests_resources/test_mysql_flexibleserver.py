# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import call, Mock

from ..azure_common import BaseTest, arm_template
from c7n_azure.resources.mysql_flexibleserver import \
    ConfigurationParametersFilter


class MySQLFlexiblerServerTest(BaseTest):

    def test_mysql_flexibleserver_schema_validate(self):
        p = self.load_policy({
            'name': 'test-mysql-flexiblerserver-schema-validate',
            'resource': 'azure.mysql-flexibleserver'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('mysql_flexibleserver.json')
    def test_find_server_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-mysql-flexibleserver',
            'resource': 'azure.mysql-flexibleserver',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestmysqlflexibleserver*'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class MySqlFlexibleServerConfigurationParameterFilterTest(BaseTest):
    @arm_template('mysqlflexibleserver.json')
    def test_server_configuration_parameter(self):
        p = self.load_policy({
            'name': 'test-azure-mysql-flexibleserver-configurations',
            'resource': 'azure.mysql-flexibleserver',
            'filters': [
                {
                    'type': 'configuration-parameter',
                    'name': 'tls_version',
                    'key': 'value',
                    'op': 'ne',
                    'value': 'TLSv1.2'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    # def test_int_value_with_regex(self):
    #     resources = self._get_test_resources()
    #     data = self._gen_filter_data(123, value_regex='test-(\\d+)', value_type='integer')
    #     mock_parameter = dict(properties=dict(value='test-123'))

    #     filter = self._get_filter(data, mock_parameter)
    #     actual = filter.process(resources)

    #     # ensure we call azure with the correct resource information
    #     filter.manager.get_client().configurations.get.assert_called_once_with(
    #         'test-group-1',
    #         'test-name-1',
    #         'test-param'
    #     )
    #     self.assertListEqual(resources, actual)

    # def test_azure_api_called_only_once_per_resource(self):
    #     resources = self._get_test_resources(2)

    #     data1 = self._gen_filter_data('123')
    #     data2 = self._gen_filter_data('456')
    #     mock_parameter = dict(properties=dict(value='test-123'))

    #     filter1 = self._get_filter(data1, mock_parameter)
    #     filter2 = self._get_filter(data2, mock_parameter)

    #     # result is unimportant for this test
    #     # also values are cached on the resource instance so calling two filters on the same
    #     # resources should not result in additional API calls
    #     filter1.process(resources)
    #     filter2.process(resources)

    #     # ensure we call azure with the correct resource information - and only once per
    #     # resource even if there are two filters (ensure the cached values are used)
    #     filter1.manager.get_client().configurations.get.assert_has_calls([
    #         call('test-group-1', 'test-name-1', 'test-param'),
    #         call('test-group-2', 'test-name-2', 'test-param')
    #     ])
    #     filter2.manager.get_client().configurations.get.assert_not_called()

    # def test_date_value(self):
    #     resources = self._get_test_resources()
    #     data = self._gen_filter_data('1/1/2023', op='lt', value_type='date')
    #     # note - str compare would be false
    #     mock_parameter = dict(properties=dict(value='5/1/2022'))

    #     filter = self._get_filter(data, mock_parameter)
    #     actual = filter.process(resources)

    #     self.assertListEqual(resources, actual)

    # def test_all_resources_passing_with_float(self):
    #     resources = self._get_test_resources()
    #     data = self._gen_filter_data('2.5', op='gt', value_type='float')
    #     mock_parameter = dict(properties=dict(value='1.5'))

    #     filter = self._get_filter(data, mock_parameter)
    #     actual = filter.process(resources)

    #     self.assertEqual(0, len(actual))

    # def test_list_op_no_match(self):
    #     resources = self._get_test_resources()
    #     data = self._gen_filter_data(['1', '2', '3', '4'], op='in')
    #     mock_parameter = dict(properties=dict(value='5'))

    #     filter = self._get_filter(data, mock_parameter)
    #     actual = filter.process(resources)

    #     self.assertEqual(0, len(actual))

    # def test_list_op_matching(self):
    #     resources = self._get_test_resources()
    #     data = self._gen_filter_data(['1', '2', '3', '4'], op='in')
    #     mock_parameter = dict(properties=dict(value='4'))

    #     filter = self._get_filter(data, mock_parameter)
    #     actual = filter.process(resources)

    #     self.assertListEqual(resources, actual)

    # def _get_test_resources(self, count=1):
    #     return [
    #         dict(name=f'test-name-{i+1}', resourceGroup=f'test-group-{i+1}', properties={})
    #         for i in range(count)
    #     ]

    # def _get_filter(self, data, configurations):
    #     client = Mock()
    #     client.configurations.get = Mock(
    #         return_value=Mock(
    #             serialize=Mock(return_value=configurations)
    #         )
    #     )

    #     manager = Mock()
    #     manager.get_client = Mock(return_value=client)

    #     return ConfigurationParametersFilter(data, manager=manager)

    # def _gen_filter_data(self, value, op='eq', value_regex=None, value_type=None,
    #         name='test-param'):
    #     return dict(
    #         type='configuration-parameter',
    #         key='value',
    #         name=name,
    #         value=value,
    #         op=op,
    #         **(dict(value_regex=value_regex) if value_regex else {}),
    #         **(dict(value_type=value_type) if value_type else {}),
    #     )