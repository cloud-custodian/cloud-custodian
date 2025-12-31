# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from azure.cosmos.cosmos_client import CosmosClient
from ..azure_common import BaseTest, arm_template, cassette_name
from c7n_azure.resources.cosmos_db import (CosmosDBChildResource, CosmosDBFirewallRulesFilter,
                                           CosmosFirewallBypassFilter,
                                           PORTAL_IPS, AZURE_CLOUD_IPS, THROUGHPUT_MULTIPLIER)
from c7n_azure.session import Session
from unittest.mock import patch, Mock
from netaddr import IPSet
from parameterized import parameterized

from c7n.utils import local_session


def get_ext_ip():
    # local external ip needs to be added to the database when recording
    from requests import get
    return get('https://checkip.amazonaws.com').text.rstrip()


def get_portal_ips():
    # https://docs.microsoft.com/en-us/azure/cosmos-db/how-to-configure-firewall?WT.mc_id=Portal-Microsoft_Azure_DocumentDB#connections-from-the-azure-portal
    return set('104.42.195.92,40.76.54.131,52.176.6.30,52.169.50.45,52.187.184.26'.split(','))


def get_azuredc_ip():
    # this means "azure datacenters only"
    return '0.0.0.0'


def get_ip_rules(ip_str):
    if ip_str == '':
        return []
    return [{'ipAddressOrRange': ip} for ip in ip_str.replace(' ', '').split(',')]


class CosmosDBTest(BaseTest):

    def setUp(self):
        super(CosmosDBTest, self).setUp()

    def test_cosmos_db_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-cosmos-db',
                'resource': 'azure.cosmosdb'
            }, validate=True)
            self.assertTrue(p)

            p = self.load_policy({
                'name': 'test-azure-cosmos-db',
                'resource': 'azure.cosmosdb-database'
            }, validate=True)
            self.assertTrue(p)

            p = self.load_policy({
                'name': 'test-azure-cosmos-db',
                'resource': 'azure.cosmosdb-collection'
            }, validate=True)
            self.assertTrue(p)

            p = self.load_policy({
                'name': 'test-azure-cosmosdb',
                'resource': 'azure.cosmosdb',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value_type': 'normalize',
                     'value': 'cctestcosmosdb*'}],
                'actions': [
                    {'type': 'set-firewall-rules',
                     'bypass-rules': ['Portal'],
                     'ip-rules': ['11.12.13.14', '21.22.23.24']
                     }
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cosmosdb.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestcosmosdb*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    def test_find_by_name_database(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-database',
            'filters': [
                {'type': 'value',
                 'key': 'id',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestcdatabase'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    def test_find_by_name_collection(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {'type': 'value',
                 'key': 'id',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cccontainer'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    def test_collection_metrics_filter(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {'type': 'value',
                 'key': 'id',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cccontainer'},
                {'type': 'metric',
                 'metric': 'ProvisionedThroughput',
                 'op': 'le',
                 'aggregation': 'average',
                 'interval': 'PT5M',
                 'threshold': 1000}
            ]
        }, validate=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    def test_database_metrics_filter(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-database',
            'filters': [
                {'type': 'value',
                 'key': 'id',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestcdatabase'},
                {'type': 'metric',
                 'metric': 'ProvisionedThroughput',
                 'op': 'le',
                 'aggregation': 'average',
                 'interval': 'PT5M',
                 'threshold': 1000}
            ]
        }, validate=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    @cassette_name('firewall_include')
    def test_firewall_rules_include(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'firewall-rules',
                 'include': [get_ext_ip()]}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('cosmosdb.json')
    @cassette_name('firewall_include')
    def test_firewall_rules_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'firewall-rules',
                 'include': [get_ext_ip() + '/32']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('cosmosdb.json')
    @cassette_name('firewall')
    def test_firewall_rules_not_equal(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'firewall-rules',
                 'equal': ['1.0.0.0/1']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @arm_template('cosmosdb.json')
    @cassette_name('firewall')
    def test_firewall_bypass(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'firewall-bypass',
                 'mode': 'equal',
                 'list': ['Portal']}]
        })
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('cosmosdb.json')
    def test_offer_collection(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {'type': 'offer',
                 'key': 'content.offerThroughput',
                 'op': 'gt',
                 'value': 100}],
        })
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('Hash', resources[0]['partitionKey']['kind'])

    @arm_template('cosmosdb.json')
    def test_store_throughput_state_collection_action(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {
                    'type': 'value',
                    'key': 'id',
                    'op': 'eq',
                    'value': 'cccontainer'
                }
            ],
            'actions': [
                {
                    'type': 'save-throughput-state',
                    'state-tag': 'test-store-throughput'
                }
            ]
        })

        collections = p.run()
        self.assertEqual(len(collections), 1)

        account_name = collections[0]['c7n:parent']['name']

        # The tag can take longer than 60 seconds to commit
        self.sleep_in_live_mode(120)

        client = local_session(Session).client(
            'azure.mgmt.cosmosdb.CosmosDBManagementClient')
        cosmos_account = client.database_accounts.get('test_cosmosdb', account_name)
        self.assertTrue('test-store-throughput' in cosmos_account.tags)

        tag_value = cosmos_account.tags['test-store-throughput']
        expected_throughput = collections[0]['c7n:offer']['content']['offerThroughput']
        expected_scaled_throughput = int(expected_throughput / THROUGHPUT_MULTIPLIER)
        expected_tag_value = '{}:{}'.format(collections[0]['_rid'], expected_scaled_throughput)
        self.assertEqual(expected_tag_value, tag_value)


class CosmosDBFirewallFilterTest(BaseTest):

    def test_query_firewall_disabled(self):
        resource = {'properties': {'ipRules': get_ip_rules(''),
                                   'isVirtualNetworkFilterEnabled': False}}
        expected = IPSet(['0.0.0.0/0'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def test_query_block_everything(self):
        resource = {'properties': {'ipRules': get_ip_rules(''),
                                   'isVirtualNetworkFilterEnabled': True}}
        expected = IPSet()
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def test_query_regular(self):
        resource = {'properties': {'ipRules': get_ip_rules('10.0.0.0/16,8.8.8.8'),
                                   'isVirtualNetworkFilterEnabled': False}}
        expected = IPSet(['10.0.0.0/16', '8.8.8.8'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def test_query_regular_plus_portal(self):
        extra = ','.join(PORTAL_IPS)
        resource = {'properties': {'ipRules': get_ip_rules(extra + ',10.0.0.0/16,8.8.8.8'),
                                   'isVirtualNetworkFilterEnabled': False}}
        expected = IPSet(['10.0.0.0/16', '8.8.8.8'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def test_query_regular_plus_cloud(self):
        extra = ', '.join(AZURE_CLOUD_IPS)
        resource = {'properties': {'ipRules': get_ip_rules(extra + ',10.0.0.0/16,8.8.8.8'),
                                   'isVirtualNetworkFilterEnabled': False}}
        expected = IPSet(['10.0.0.0/16', '8.8.8.8'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def test_query_regular_plus_portal_cloud(self):
        extra = ','.join(PORTAL_IPS + AZURE_CLOUD_IPS)
        resource = {'properties': {'ipRules': get_ip_rules(extra + ',10.0.0.0/16,8.8.8.8'),
                                   'isVirtualNetworkFilterEnabled': False}}
        expected = IPSet(['10.0.0.0/16', '8.8.8.8'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def test_query_regular_plus_partial_cloud(self):
        extra = ','.join(PORTAL_IPS[1:])
        resource = {'properties': {'ipRules': get_ip_rules(extra + ',10.0.0.0/16,8.8.8.8'),
                                   'isVirtualNetworkFilterEnabled': False}}
        expected = IPSet(['10.0.0.0/16', '8.8.8.8'] + PORTAL_IPS[1:])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def _get_filter(self, mode='equal'):
        data = {mode: ['10.0.0.0/8', '127.0.0.1']}
        return CosmosDBFirewallRulesFilter(data, Mock())


class CosmosDBFirewallBypassFilterTest(BaseTest):

    scenarios = [
        [get_ip_rules(''), False, ['AzureCloud', 'Portal']],
        [get_ip_rules(''), True, []],
        [get_ip_rules('1.0.0.0'), True, []],
        [get_ip_rules(','.join(AZURE_CLOUD_IPS)), False, ['AzureCloud']],
        [get_ip_rules(','.join(PORTAL_IPS)), False, ['Portal']],
        [get_ip_rules(','.join(AZURE_CLOUD_IPS + PORTAL_IPS)), False, ['AzureCloud', 'Portal']],
        [get_ip_rules(','.join(AZURE_CLOUD_IPS + ['10.0.0.8'])), False, ['AzureCloud']],
        [get_ip_rules(','.join(PORTAL_IPS + ['10.0.0.8'])), False, ['Portal']],
        [get_ip_rules(','.join(AZURE_CLOUD_IPS + PORTAL_IPS + ['10.0.0.8'])), False,
         ['AzureCloud', 'Portal']],
    ]

    @parameterized.expand(scenarios)
    def test_run(self, ip_range, vnet_filter_enabled, expected):
        resource = {'properties': {'ipRules': ip_range,
                                   'isVirtualNetworkFilterEnabled': vnet_filter_enabled}}
        f = CosmosFirewallBypassFilter({'mode': 'equal', 'list': []}, Mock())
        self.assertEqual(expected, f._query_bypass(resource))


class CosmosDBFirewallActionTest(BaseTest):

    @patch('azure.mgmt.cosmosdb.operations._database_accounts_operations.'
           'DatabaseAccountsOperations.begin_create_or_update')
    @arm_template('cosmosdb.json')
    @cassette_name('firewall_action')
    def test_set_ip_range_filter_append(self, update_mock):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestcosmosdb*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'append': True,
                 'ip-rules': ['11.12.13.14', '21.22.23.24']
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        self.assertEqual(1, len(update_mock.mock_calls))
        _, args, kwargs = update_mock.mock_calls[0]

        expected = set(['11.12.13.14', '21.22.23.24', get_ext_ip()])
        expected.update(get_portal_ips())
        actual = set([ip['ipAddressOrRange']
                      for ip in kwargs['create_update_parameters']['properties']['ipRules']])

        self.assertEqual(resources[0]['resourceGroup'], args[0])
        self.assertEqual(resources[0]['name'], args[1])
        self.assertEqual(expected, actual)

    @patch('azure.mgmt.cosmosdb.operations._database_accounts_operations.'
           'DatabaseAccountsOperations.begin_create_or_update')
    @arm_template('cosmosdb.json')
    @cassette_name('firewall_action')
    def test_set_ip_range_filter_replace(self, update_mock):
        ext_ip = get_ext_ip()
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestcosmosdb*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'append': False,
                 'ip-rules': [ext_ip, '11.12.13.14', '21.22.23.24']
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        self.assertEqual(1, len(update_mock.mock_calls))
        _, args, kwargs = update_mock.mock_calls[0]

        expected = set(['11.12.13.14', '21.22.23.24', ext_ip])
        expected.update(get_portal_ips())
        actual = set([ip['ipAddressOrRange']
                      for ip in kwargs['create_update_parameters']['properties']['ipRules']])

        self.assertEqual(resources[0]['resourceGroup'], args[0])
        self.assertEqual(resources[0]['name'], args[1])
        self.assertEqual(expected, actual)

    @patch('azure.mgmt.cosmosdb.operations._database_accounts_operations.'
           'DatabaseAccountsOperations.begin_create_or_update')
    @arm_template('cosmosdb.json')
    @cassette_name('firewall_action')
    def test_set_ip_range_filter_replace_bypass(self, update_mock):
        ext_ip = get_ext_ip()
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestcosmosdb*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'append': False,
                 'bypass-rules': ['Portal', 'AzureCloud'],
                 'ip-rules': [ext_ip, '11.12.13.14', '21.22.23.24']
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        self.assertEqual(1, len(update_mock.mock_calls))
        _, args, kwargs = update_mock.mock_calls[0]

        expected = set(['11.12.13.14', '21.22.23.24', ext_ip, get_azuredc_ip()])
        expected.update(get_portal_ips())
        actual = set([ip['ipAddressOrRange']
                      for ip in kwargs['create_update_parameters']['properties']['ipRules']])

        self.assertEqual(resources[0]['resourceGroup'], args[0])
        self.assertEqual(resources[0]['name'], args[1])
        self.assertEqual(expected, actual)

    @patch('azure.mgmt.cosmosdb.operations._database_accounts_operations.'
           'DatabaseAccountsOperations.begin_create_or_update')
    @arm_template('cosmosdb.json')
    @cassette_name('firewall_action')
    def test_set_ip_range_filter_remove_bypass(self, update_mock):
        ext_ip = get_ext_ip()
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestcosmosdb*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'append': False,
                 'bypass-rules': [],
                 'ip-rules': [ext_ip, '21.22.23.24']
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        self.assertEqual(1, len(update_mock.mock_calls))
        _, args, kwargs = update_mock.mock_calls[0]

        self.assertEqual(resources[0]['resourceGroup'], args[0])
        self.assertEqual(resources[0]['name'], args[1])

        expected = set(['21.22.23.24', ext_ip])
        actual = set([ip['ipAddressOrRange']
                      for ip in kwargs['create_update_parameters']['properties']['ipRules']])

        self.assertEqual(expected, actual)

    @patch('azure.mgmt.cosmosdb.operations._database_accounts_operations.'
           'DatabaseAccountsOperations.begin_create_or_update')
    @arm_template('cosmosdb.json')
    @cassette_name('firewall_action')
    def test_set_vnet_append(self, update_mock):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestcosmosdb*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'append': True,
                 'virtual-network-rules': ['id1', 'id2'],
                 'ip-rules': ['11.12.13.14', '21.22.23.24']
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        _, args, kwargs = update_mock.mock_calls[0]

        expected = set(['11.12.13.14', '21.22.23.24', get_ext_ip()])
        expected.update(get_portal_ips())
        actual = set([ip['ipAddressOrRange']
                      for ip in kwargs['create_update_parameters']['properties']['ipRules']])

        self.assertEqual(resources[0]['resourceGroup'], args[0])
        self.assertEqual(resources[0]['name'], args[1])
        self.assertEqual(expected, actual)
        self.assertEqual(
            {'id1', 'id2'},
            {r.id for r in
             kwargs['create_update_parameters']['properties']['virtualNetworkRules']})


class CosmosDBThroughputActionsTest(BaseTest):
    def setUp(self, *args, **kwargs):
        super(CosmosDBThroughputActionsTest, self).setUp(*args, **kwargs)
        self.client = local_session(Session).client(
            'azure.mgmt.cosmosdb.CosmosDBManagementClient')
        sub_id = local_session(Session).get_subscription_id()[-12:]
        account_name = "cctestcosmosdb%s" % sub_id
        key = CosmosDBChildResource.get_cosmos_key(
            'test_cosmosdb', account_name, self.client, readonly=False)
        self.data_client = CosmosClient(
            url_connection='https://%s.documents.azure.com:443/' % account_name,
            auth={
                'masterKey': key
            }
        )
        self.offer = None

    def tearDown(self, *args, **kwargs):
        super(CosmosDBThroughputActionsTest, self).tearDown(*args, **kwargs)
        if self.offer:
            self.offer['content']['offerThroughput'] = 400
            self.data_client.ReplaceOffer(
                self.offer['_self'],
                self.offer
            )

    @cassette_name('test_replace_offer_collection_action')
    def test_replace_offer_collection_action(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {
                    'type': 'value',
                    'key': 'id',
                    'op': 'eq',
                    'value': 'cccontainer'
                },
                {
                    'type': 'offer',
                    'key': 'content.offerThroughput',
                    'op': 'eq',
                    'value': 400
                }
            ],
            'actions': [
                {
                    'type': 'replace-offer',
                    'throughput': 500
                }
            ]
        })
        collections = p.run()
        self.offer = collections[0]['c7n:offer']

        self.assertEqual(len(collections), 1)
        self._assert_offer_throughput_equals(500, collections[0]['_self'])

    @cassette_name('test_restore_throughput_state_updates_throughput_from_tag')
    def test_restore_throughput_state_updates_throughput_from_tag(self):

        p1 = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {
                    'type': 'value',
                    'key': 'id',
                    'op': 'eq',
                    'value': 'cccontainer'
                }
            ],
            'actions': [
                {
                    'type': 'save-throughput-state',
                    'state-tag': 'test-restore-throughput'
                }
            ]
        })

        collections = p1.run()
        self.assertEqual(len(collections), 1)

        collection_offer = collections[0]['c7n:offer']
        self.offer = collection_offer

        throughput_to_restore = collection_offer['content']['offerThroughput']

        collection_offer['content']['offerThroughput'] = throughput_to_restore + 100

        self.data_client.ReplaceOffer(
            collection_offer['_self'],
            collection_offer
        )

        self._assert_offer_throughput_equals(throughput_to_restore + 100, collections[0]['_self'])

        p2 = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {
                    'type': 'value',
                    'key': 'id',
                    'op': 'eq',
                    'value': 'cccontainer'
                },
            ],
            'actions': [
                {
                    'type': 'restore-throughput-state',
                    'state-tag': 'test-restore-throughput'
                }
            ]
        })

        collections = p2.run()

        self.assertEqual(len(collections), 1)
        self._assert_offer_throughput_equals(throughput_to_restore, collections[0]['_self'])

    def _assert_offer_throughput_equals(self, throughput, resource_self):
        self.sleep_in_live_mode()
        offers = self.data_client.ReadOffers()
        offer = next((o for o in offers if o['resource'] == resource_self), None)
        self.assertIsNotNone(offer)
        self.assertEqual(throughput, offer['content']['offerThroughput'])
