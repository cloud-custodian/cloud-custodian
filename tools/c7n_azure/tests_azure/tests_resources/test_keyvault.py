# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from ..azure_common import BaseTest, arm_template, cassette_name
from c7n_azure.resources.key_vault import (KeyVaultUpdateAccessPolicyAction, WhiteListFilter,
                                           KeyVaultFirewallRulesFilter,
                                           KeyVaultFirewallBypassFilter)
from c7n_azure.session import Session
from c7n_azure.utils import GraphHelper
from mock import patch, Mock
from azure.core.exceptions import HttpResponseError
from netaddr import IPSet
from parameterized import parameterized
import pytest
from requests import Response

from c7n.utils import local_session


class KeyVaultTest(BaseTest):
    def setUp(self):
        super(KeyVaultTest, self).setUp()

    def test_key_vault_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-key-vault',
                'resource': 'azure.keyvault',
                'filters': [
                    {'type': 'whitelist',
                     'key': 'test'}
                ],
                'actions': [
                    {'type': 'update-access-policy',
                     'operation': 'add',
                     'access-policies': []}
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault1*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_compare_permissions(self):
        p1 = {"keys": ['get'], "secrets": ['get'], "certificates": ['get']}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertTrue(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {"keys": ['delete']}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertFalse(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {"secrets": ['delete']}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertFalse(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {"certificates": ['delete']}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertFalse(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertTrue(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {"keys": ['get'], "secrets": ['get'], "certificates": ['get']}
        p2 = {}
        self.assertFalse(WhiteListFilter.compare_permissions(p1, p2))

    # Requires Graph access
    @arm_template('keyvault.json')
    @pytest.mark.skiplive
    def test_whitelist(self):
        """Tests basic whitelist functionality"""
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault1*'},
                {'not': [
                    {'type': 'whitelist',
                     'key': 'principalName',
                     'users': ['account1@sample.com']}
                ]}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault-no-policies.json')
    def test_whitelist_zero_access_policies(self):
        """Tests that a keyvault with 0 access policies is processed properly
        and doesn't raise an exception.
        """
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault2*'},
                {'not': [
                    {'type': 'whitelist',
                     'key': 'principalName',
                     'users': ['account1@sample.com']}
                ]}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('keyvault.json')
    @patch.object(GraphHelper, 'get_principal_dictionary')
    def test_whitelist_not_authorized(self, get_principal_dictionary):
        """Tests that an exception is thrown when both:
          The Microsoft Graph call fails.

          This is mocked because it is impractical to have
          identities with varying levels of graph access for
          live test runs or recordings"""

        mock_response = Mock(spec=Response)
        mock_response.status_code = 403
        mock_response.reason = 'forbidden'
        get_principal_dictionary.side_effect = HttpResponseError(response=mock_response)

        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault1*'},
                {'not': [
                    {'type': 'whitelist',
                     'key': 'principalName',
                     'users': ['account1@sample.com']}
                ]}
            ]
        })

        with self.assertRaises(HttpResponseError) as e:
            p.run()

        self.assertEqual(403, e.exception.status_code)

    def test_update_access_policy_action(self):
        with patch(self._get_key_vault_client_string() + '.update_access_policy')\
                as access_policy_action_mock:
            p = self.load_policy({
                'name': 'test-azure-keyvault',
                'resource': 'azure.keyvault',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value_type': 'normalize',
                     'value': 'cckeyvault1*'}],
                'actions': [
                    {'type': 'update-access-policy',
                     'operation': 'replace',
                     'access-policies': [{
                         'tenant-id': '00000000-0000-0000-0000-000000000000',
                         'object-id': '11111111-1111-1111-1111-111111111111',
                         'permissions': {'keys': ['Get']}}]}]
            })

            p.run()
            access_policy_action_mock.assert_called()

    def test_transform_access_policies(self):
        mock_access_policies = [{"object-id": "mockObjectId",
                                 "tenant-id": "mockTenantId",
                                 "permissions": {"keys": ["Get"]}}]
        transformed_access_policies = KeyVaultUpdateAccessPolicyAction._transform_access_policies(
            mock_access_policies).get("accessPolicies")[0]
        self.assertTrue("objectId" in transformed_access_policies)
        self.assertTrue("tenantId" in transformed_access_policies)
        self.assertTrue("permissions" in transformed_access_policies)

    def _get_key_vault_client_string(self):
        client = local_session(Session) \
            .client('azure.mgmt.keyvault.KeyVaultManagementClient').vaults
        return client.__module__ + '.' + client.__class__.__name__

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_firewall_rules_include(self):
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cckeyvault1*'},
                {'type': 'firewall-rules',
                 'include': ['1.0.0.0']}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_firewall_rules_not_include_all_ranges(self):
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cckeyvault1*'},
                {'type': 'firewall-rules',
                 'include': ['1.0.0.0', '127.0.0.1']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_firewall_rules_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cckeyvault1*'},
                {'type': 'firewall-rules',
                 'include': ['128.0.0.0/1']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_firewall_rules_not_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cckeyvault1*'},
                {'type': 'firewall-rules',
                 'include': ['127.0.0.0/8']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_firewall_rules_equal(self):
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cckeyvault1*'},
                {'type': 'firewall-rules',
                 'equal': ['0.0.0.0-126.255.255.255', '128.0.0.0-255.255.255.255']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_firewall_rules_not_equal(self):
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cckeyvault1*'},
                {'type': 'firewall-rules',
                 'equal': ['0.0.0.0-126.255.255.255', '128.0.0.0-255.255.255.254']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_firewall_bypass(self):
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'firewall-bypass',
                 'mode': 'equal',
                 'list': ['AzureServices']}],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('keyvault.json')
    def test_update_access_policy(self):
        tenant_id = '00000000-0000-0000-0000-000000000000'
        object_id = '11111111-1111-1111-1111-111111111111'
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cckeyvault1*'}],
            'actions': [
                {'type': 'update-access-policy',
                    'operation': 'add',
                    'access-policies': [{
                        'tenant-id': tenant_id,
                        'object-id': object_id,
                        'permissions': {'keys': ['Get']}}]}]
        })
        warnings = self.capture_logging('custodian.azure.keyvault', level=logging.WARNING)
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(warnings.getvalue(), '')
        vault_before = resources[0]

        client = self.session.client('azure.mgmt.keyvault.KeyVaultManagementClient')
        vault_after = client.vaults.get(
            vault_before['resourceGroup'], vault_before['name']
        ).serialize(True)

        access_policy_expr = f"length(properties.accessPolicies[?objectId == '{object_id}'])"
        self.assertJmes(
            access_policy_expr,
            vault_before,
            0
        )
        self.assertJmes(
            access_policy_expr,
            vault_after,
            1
        )


class KeyVaultFirewallFilterTest(BaseTest):

    def test_query_empty_network_acl(self):
        resource = {'properties': {}}
        expected = IPSet(['0.0.0.0/0'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def test_query_default_action_allow(self):
        resource = {'properties': {'networkAcls': {'defaultAction': 'Allow'}}}
        expected = IPSet(['0.0.0.0/0'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def test_query_default_action_deny(self):
        resource = {'properties': {'networkAcls': {'defaultAction': 'Deny',
                                                   'ipRules': [{'value': '10.0.0.0/16'},
                                                               {'value': '8.8.8.8'}]}}}
        expected = IPSet(['8.8.8.8', '10.0.0.0/16'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def _get_filter(self, mode='equal'):
        data = {mode: ['10.0.0.0/8', '127.0.0.1']}
        return KeyVaultFirewallRulesFilter(data, Mock())


class KeyVaultFirewallBypassFilterTest(BaseTest):

    scenarios = [
        [{}, []],
        [{'networkAcls': {'defaultAction': 'Allow', 'bypass': ''}}, ['AzureServices']],
        [{'networkAcls': {'defaultAction': 'Deny', 'bypass': ''}}, []],
        [{'networkAcls': {'defaultAction': 'Deny', 'bypass': 'AzureServices'}},
         ['AzureServices']],
    ]

    @parameterized.expand(scenarios)
    def test_run(self, properties, expected):
        resource = {'properties': properties}
        f = KeyVaultFirewallBypassFilter({'mode': 'equal', 'list': []})

        self.assertEqual(expected, f._query_bypass(resource))


class KeyVaultUpdateActionTest(BaseTest):

    @arm_template("keyvault.json")
    def test_update_action(self):
        p = self.load_policy(
            {
                'name': 'test-azure-keyvault',
                'resource': 'azure.keyvault',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value_type': 'normalize',
                        'value': 'cckeyvault1*'
                    },
                    {
                        "properties.publicNetworkAccess": "Enabled"
                    }
                ],
                'actions': [
                    {
                        "type": "update",
                        "configuration": {
                            "tenant_id": "keep",
                            "sku": {"current": True},
                            "public_network_access": "disabled",
                        }
                    }
                ]
            }
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        vault_before = resources[0]

        client = self.session.client('azure.mgmt.keyvault.KeyVaultManagementClient')
        vault_after = client.vaults.get(
            vault_before['resourceGroup'], vault_before['name']
        )
        assert vault_after.properties.public_network_access == "Disabled"

    @arm_template("keyvault.json")
    def test_update_action_network_access(self):
        sub = "ea42f556-5106-4743-99b0-c129bfa71a47"
        rg = "test_keyvault"
        id_prefix = f"/subscriptions/{sub}/resourceGroups/{rg}/providers"
        subnet_id = f"{id_prefix}/Microsoft.Network/virtualNetworks/test/subnets/default"

        p = self.load_policy(
            {
                'name': 'test-azure-keyvault',
                'resource': 'azure.keyvault',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value_type': 'normalize',
                        'value': 'cckeyvault1*'
                    },
                ],
                'actions': [
                    {
                        "type": "update",
                        "configuration": {
                            "tenant_id": "keep",
                            "sku": {"current": True},
                            "network_acls": {
                                "bypass": "None",
                                "default_action": "Allow",
                                "ip_rules": [
                                    {
                                        "value": "123.45.67.89"
                                    }
                                ],
                                "virtual_network_rules": [
                                    {
                                        "id": subnet_id,
                                        "ignore_missing_vnet_service_endpoint": True
                                    }
                                ]

                            }
                        }
                    }
                ]
            }
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        vault_before = resources[0]

        # all the network acls before were the default from the arm template
        assert vault_before['properties']['networkAcls']['bypass'] == "AzureServices"

        client = self.session.client('azure.mgmt.keyvault.KeyVaultManagementClient')
        vault_after = client.vaults.get(
            vault_before['resourceGroup'], vault_before['name']
        )

        assert vault_after.properties.network_acls.bypass == "None"
        assert vault_after.properties.network_acls.default_action == "Allow"

        assert len(vault_after.properties.network_acls.ip_rules) == 1
        # azure inserts the /32
        assert vault_after.properties.network_acls.ip_rules[0].value == "123.45.67.89/32"

        assert len(vault_after.properties.network_acls.virtual_network_rules) == 1
        vn_rules = vault_after.properties.network_acls.virtual_network_rules[0]

        # azure lowercases the id string
        assert vn_rules.id == subnet_id.lower()
        assert vn_rules.ignore_missing_vnet_service_endpoint is True
