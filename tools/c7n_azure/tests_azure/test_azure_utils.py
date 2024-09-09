# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import sys
import time
import types

import pytest
from azure.mgmt.managementgroups.models import DescendantInfo
from c7n_azure.tags import TagHelper
from c7n_azure.utils import (AppInsightsHelper, ManagedGroupHelper, Math,
                             PortsRangeHelper, ResourceIdParser, StringUtils,
                             custodian_azure_send_override,
                             get_keyvault_auth_endpoint, get_keyvault_secret,
                             get_service_tag_ip_space, is_resource_group,
                             is_resource_group_id)
from mock import Mock, patch
from msrestazure.azure_cloud import AZURE_CHINA_CLOUD, AZURE_PUBLIC_CLOUD

from .azure_common import DEFAULT_SUBSCRIPTION_ID, BaseTest

try:
    from importlib import reload
except Exception:
    pass  # Python 2.7 has reload built-in

RESOURCE_ID = (
    "/subscriptions/%s/resourceGroups/"
    "rgtest/providers/Microsoft.Compute/virtualMachines/nametest" % DEFAULT_SUBSCRIPTION_ID)


RESOURCE_ID_CHILD = (
    "/subscriptions/%s/resourceGroups/"
    "rgtest/providers/Microsoft.Sql/servers/testserver/"
    "databases/testdb" % DEFAULT_SUBSCRIPTION_ID)

GUID = '00000000-0000-0000-0000-000000000000'


def _get_descendant_info(**kwargs):
    info = DescendantInfo()
    for k, v in kwargs.items():
        setattr(info, k, v)
    return info


class UtilsTest(BaseTest):
    def setUp(self):
        super(UtilsTest, self).setUp()

    def test_get_subscription_id(self):
        self.assertEqual(ResourceIdParser.get_subscription_id(RESOURCE_ID), DEFAULT_SUBSCRIPTION_ID)

    def test_get_namespace(self):
        self.assertEqual(ResourceIdParser.get_namespace(RESOURCE_ID), "Microsoft.Compute")
        self.assertEqual(ResourceIdParser.get_namespace(RESOURCE_ID_CHILD), "Microsoft.Sql")

    def test_get_resource_group(self):
        self.assertEqual(ResourceIdParser.get_resource_group(RESOURCE_ID), "rgtest")

    def test_get_resource_type(self):

        self.assertEqual(ResourceIdParser.get_resource_type(RESOURCE_ID), "virtualMachines")
        self.assertEqual(ResourceIdParser.get_resource_type(RESOURCE_ID_CHILD), "servers/databases")

    def test_get_full_type(self):
        self.assertEqual(ResourceIdParser.get_full_type(RESOURCE_ID),
                         "Microsoft.Compute/virtualMachines")

    def test_resource_name(self):
        self.assertEqual(ResourceIdParser.get_resource_name(RESOURCE_ID), "nametest")

    def test_math_mean(self):
        self.assertEqual(Math.mean([4, 5, None, 3]), 4)
        self.assertEqual(Math.mean([None]), 0)
        self.assertEqual(Math.mean([3, 4]), 3.5)

    def test_math_sum(self):
        self.assertEqual(Math.sum([4, 5, None, 3]), 12)
        self.assertEqual(Math.sum([None]), 0)
        self.assertEqual(Math.sum([3.5, 4]), 7.5)

    def test_string_utils_equal(self):
        # Case insensitive matches
        self.assertTrue(StringUtils.equal("FOO", "foo"))
        self.assertTrue(StringUtils.equal("fOo", "FoO"))
        self.assertTrue(StringUtils.equal("ABCDEFGH", "abcdefgh"))
        self.assertFalse(StringUtils.equal("Foo", "Bar"))

        # Case sensitive matches
        self.assertFalse(StringUtils.equal("Foo", "foo", False))
        self.assertTrue(StringUtils.equal("foo", "foo", False))
        self.assertTrue(StringUtils.equal("fOo", "fOo", False))
        self.assertFalse(StringUtils.equal("Foo", "Bar"))

        # Strip whitespace matches
        self.assertTrue(StringUtils.equal(" Foo ", "foo"))
        self.assertTrue(StringUtils.equal("Foo", " foo "))
        self.assertTrue(StringUtils.equal(" Foo ", "Foo", False))
        self.assertTrue(StringUtils.equal("Foo", " Foo ", False))

        # Returns false for non string types
        self.assertFalse(StringUtils.equal(1, "foo"))
        self.assertFalse(StringUtils.equal("foo", 1))
        self.assertFalse(StringUtils.equal(True, False))

    def test_get_tag_value(self):
        resource = {'tags': {'tag1': 'value1', 'tAg2': 'VaLuE2', 'TAG3': 'VALUE3'}}

        self.assertEqual(TagHelper.get_tag_value(resource, 'tag1', True), 'value1')
        self.assertEqual(TagHelper.get_tag_value(resource, 'tag2', True), 'VaLuE2')
        self.assertEqual(TagHelper.get_tag_value(resource, 'tag3', True), 'VALUE3')

    def test_get_ports(self):
        self.assertEqual(PortsRangeHelper.get_ports_set_from_string("5, 4-5, 9"), {4, 5, 9})
        rule = {'properties': {'destinationPortRange': '10-12'}}
        self.assertEqual(PortsRangeHelper.get_ports_set_from_rule(rule), {10, 11, 12})
        rule = {'properties': {'destinationPortRanges': ['80', '10-12']}}
        self.assertEqual(PortsRangeHelper.get_ports_set_from_rule(rule), {10, 11, 12, 80})
        rule = {'properties': {
            'destinationPortRange': '', 'destinationPortRanges': ['80', '10-12']}}
        self.assertEqual(PortsRangeHelper.get_ports_set_from_rule(rule), {10, 11, 12, 80})

    def test_validate_ports_string(self):
        self.assertEqual(PortsRangeHelper.validate_ports_string('80'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('22-26'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('80,22'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('80,22-26'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('80,22-26,30-34'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('65537'), False)
        self.assertEqual(PortsRangeHelper.validate_ports_string('-1'), False)
        self.assertEqual(PortsRangeHelper.validate_ports_string('10-8'), False)
        self.assertEqual(PortsRangeHelper.validate_ports_string('80,30,25-65538'), False)
        self.assertEqual(PortsRangeHelper.validate_ports_string('65536-65537'), False)

    def test_get_ports_strings_from_list(self):
        self.assertEqual(PortsRangeHelper.get_ports_strings_from_list([]),
                         [])
        self.assertEqual(PortsRangeHelper.get_ports_strings_from_list([10, 11]),
                         ['10-11'])
        self.assertEqual(PortsRangeHelper.get_ports_strings_from_list([10, 12, 13, 14]),
                         ['10', '12-14'])
        self.assertEqual(PortsRangeHelper.get_ports_strings_from_list([10, 12, 13, 14, 20, 21, 22]),
                         ['10', '12-14', '20-22'])

    def test_build_ports_dict(self):
        securityRules = [
            {'properties': {'destinationPortRange': '80-84',
                            'priority': 100,
                            'direction': 'Outbound',
                            'access': 'Allow',
                            'protocol': 'TCP'}},
            {'properties': {'destinationPortRange': '85-89',
                            'priority': 110,
                            'direction': 'Outbound',
                            'access': 'Allow',
                            'protocol': 'UDP'}},
            {'properties': {'destinationPortRange': '80-84',
                            'priority': 120,
                            'direction': 'Inbound',
                            'access': 'Deny',
                            'protocol': 'TCP'}},
            {'properties': {'destinationPortRange': '85-89',
                            'priority': 130,
                            'direction': 'Inbound',
                            'access': 'Deny',
                            'protocol': 'UDP'}},
            {'properties': {'destinationPortRange': '80-89',
                            'priority': 140,
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': '*'}}]
        nsg = {'properties': {'securityRules': securityRules}}

        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Inbound', 'TCP'),
                         {k: k > 84 for k in range(80, 90)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Inbound', 'UDP'),
                         {k: k < 85 for k in range(80, 90)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Inbound', '*'),
                         {k: False for k in range(80, 90)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Outbound', 'TCP'),
                         {k: True for k in range(80, 85)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Outbound', 'UDP'),
                         {k: True for k in range(85, 90)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Outbound', '*'),
                         {k: True for k in range(80, 90)})

    def test_snake_to_camel(self):
        self.assertEqual(StringUtils.snake_to_camel(""), "")
        self.assertEqual(StringUtils.snake_to_camel("test"), "test")
        self.assertEqual(StringUtils.snake_to_camel("test_abc"), "testAbc")
        self.assertEqual(StringUtils.snake_to_camel("test_abc_def"), "testAbcDef")

    def test_naming_hash(self):
        source = 'Lorem ipsum dolor sit amet'
        source2 = 'amet sit dolor ipsum Lorem'
        self.assertEqual(StringUtils.naming_hash(source), '16aba539')
        self.assertEqual(StringUtils.naming_hash(source, 10), '16aba5393a')
        self.assertNotEqual(StringUtils.naming_hash(source), StringUtils.naming_hash(source2))

    @patch('azure.mgmt.applicationinsights.v2015_05_01.operations.ComponentsOperations.get',
           return_value=type(str('result_data'), (), {'instrumentation_key': GUID}))
    def test_app_insights_get_instrumentation_key(self, mock_handler_run):
        self.assertEqual(AppInsightsHelper.get_instrumentation_key('azure://' + GUID), GUID)
        self.assertEqual(AppInsightsHelper.get_instrumentation_key('azure://resourceGroup/name'),
                         GUID)
        mock_handler_run.assert_called_once_with('resourceGroup', 'name')

    @patch('c7n_azure.utils.send_logger.debug')
    def test_custodian_azure_send_override_200(self, logger):
        mock = Mock()
        mock.send = types.MethodType(custodian_azure_send_override, mock)

        response_dict = {
            'headers': {'x-ms-ratelimit-remaining-subscription-reads': '12000'},
            'status_code': 200
        }
        mock.orig_send.return_value = type(str('response'), (), response_dict)
        mock.send('')

        self.assertEqual(mock.orig_send.call_count, 1)
        self.assertEqual(logger.call_count, 2)

    @patch('c7n_azure.utils.send_logger.debug')
    @patch('c7n_azure.utils.send_logger.warning')
    def test_custodian_azure_send_override_429(self, logger_debug, logger_warning):
        mock = Mock()
        mock.send = types.MethodType(custodian_azure_send_override, mock)

        response_dict = {
            'headers': {'Retry-After': 0},
            'status_code': 429
        }
        mock.orig_send.return_value = type(str('response'), (), response_dict)
        mock.send('')

        self.assertEqual(mock.orig_send.call_count, 8)
        self.assertEqual(logger_debug.call_count, 8)
        self.assertEqual(logger_warning.call_count, 8)

    @patch('c7n_azure.utils.send_logger.error')
    def test_custodian_azure_send_override_429_long_retry(self, logger):
        mock = Mock()
        mock.send = types.MethodType(custodian_azure_send_override, mock)

        response_dict = {
            'headers': {'Retry-After': 60},
            'status_code': 429
        }
        mock.orig_send.return_value = type(str('response'), (), response_dict)
        mock.send('')

        self.assertEqual(mock.orig_send.call_count, 1)
        self.assertEqual(logger.call_count, 1)

    @patch('c7n_azure.utils.send_logger.debug')
    @patch('c7n_azure.utils.send_logger.warning')
    def test_custodian_azure_send_override_429_missingheader(self, logger_debug, logger_warning):
        mock = Mock()
        mock.send = types.MethodType(custodian_azure_send_override, mock)

        response_dict = {
            'headers': {},
            'status_code': 429
        }
        mock.orig_send.return_value = type(str('response'), (), response_dict)

        with patch('time.sleep', new_callable=time.sleep(0)):
            mock.send('')

        self.assertEqual(mock.orig_send.call_count, 7)
        self.assertEqual(logger_debug.call_count, 6)
        self.assertEqual(logger_warning.call_count, 7)

    managed_group_return_value = [
        _get_descendant_info(type='managementGroups/subscriptions', name=DEFAULT_SUBSCRIPTION_ID),
        _get_descendant_info(type='Microsoft.Management/managementGroups'),
        _get_descendant_info(type='Microsoft.Management/managementGroups/subscriptions', name=GUID)
    ]

    @patch((
        'azure.mgmt.managementgroups.operations'
        '.ManagementGroupsOperations.get_descendants'),
        return_value=managed_group_return_value)
    def test_managed_group_helper(self, _1):
        sub_ids = ManagedGroupHelper.get_subscriptions_list('test-group', self.session)
        self.assertEqual(sub_ids, [DEFAULT_SUBSCRIPTION_ID, GUID])

    def test_get_keyvault_secret(self):
        mock = Mock()
        mock.value = '{"client_id": "client", "client_secret": "secret"}'
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__',
                   return_value=None), \
                patch('azure.keyvault.secrets.SecretClient.get_secret', return_value=mock):

            reload(sys.modules['c7n_azure.utils'])

            result = get_keyvault_secret(None, 'https://testkv.vault.net/secrets/testsecret/123412')
            self.assertEqual(mock.value, result)

    # Test relies on substitute data in Azure Common, not designed for live data
    @pytest.mark.skiplive
    def test_get_service_tag_ip_space(self):
        # Get with region
        result = get_service_tag_ip_space('ApiManagement', 'WestUS')
        self.assertEqual(3, len(result))
        self.assertEqual({"13.64.39.16/32",
                          "40.112.242.148/31",
                          "40.112.243.240/28"}, set(result))

        # Get without region
        result = get_service_tag_ip_space('ApiManagement')
        self.assertEqual(5, len(result))
        self.assertEqual({"13.69.64.76/31",
                          "13.69.66.144/28",
                          "23.101.67.140/32",
                          "51.145.179.78/32",
                          "137.117.160.56/32"}, set(result))

        # Invalid tag
        result = get_service_tag_ip_space('foo')
        self.assertEqual(0, len(result))

    def test_is_resource_group_id(self):
        self.assertTrue(is_resource_group_id('/subscriptions/GUID/resourceGroups/rg'))
        self.assertTrue(is_resource_group_id('/subscriptions/GUID/resourceGroups/rg/'))
        self.assertTrue(is_resource_group_id('/Subscriptions/GUID/resourcegroups/rg'))

        self.assertFalse(is_resource_group_id('/subscriptions/GUID/rg/'))
        self.assertFalse(is_resource_group_id('subscriptions/GUID/rg/'))
        self.assertFalse(is_resource_group_id('/GUID/rg/'))
        self.assertFalse(is_resource_group_id('/subscriptions/GUID/rg/providers/vm/vm'))
        self.assertFalse(is_resource_group_id('/subscriptions/GUID/rg/providers'))
        self.assertFalse(is_resource_group_id('/subscriptions/GUID/rg/p'))

    def test_is_resource_group(self):
        self.assertTrue(is_resource_group({'type': 'resourceGroups'}))
        self.assertFalse(is_resource_group({'type': 'virtualMachines'}))

    def test_get_keyvault_auth_public(self):
        auth = get_keyvault_auth_endpoint(AZURE_PUBLIC_CLOUD)
        self.assertEqual('https://vault.azure.net', auth)

    def test_get_keyvault_auth_china(self):
        auth = get_keyvault_auth_endpoint(AZURE_CHINA_CLOUD)
        self.assertEqual('https://vault.azure.cn', auth)
