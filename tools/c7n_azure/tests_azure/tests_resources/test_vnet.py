# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from msrestazure.tools import parse_resource_id

from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n_azure.session import Session

from ..azure_common import BaseTest, DEFAULT_SUBSCRIPTION_ID, arm_template


class VnetTest(BaseTest):
    def test_vnet_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-vnet',
                'resource': 'azure.vnet'
            }, validate=True)
            self.assertTrue(p)


class VnetFlowLogsFilterTest(BaseTest):
    def test_flow_log_filter_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-vnet',
                'resource': 'azure.vnet',
                'filters': [
                    {
                        'or': [
                            {
                                'type': 'flow-logs',
                                'key': 'logs',
                                'value': 'empty'
                            },
                            {
                                'and': [
                                    {
                                        'type': 'flow-logs',
                                        'key': 'logs[0].retentionPolicy.days',
                                        'op': 'ne',
                                        'value': 0
                                    },
                                    {
                                        'type': 'flow-logs',
                                        'key': 'logs[0].retentionPolicy.days',
                                        'op': 'lt',
                                        'value': 90
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_flow_log_filter_no_logs(self):
        p = self.load_policy({
            'name': 'test-azure-vnet',
            'resource': 'azure.vnet',
            'filters': [
                {'type': 'value', 'key': 'name', 'value': 'c7n-vnet-no-flowlog'},
                {
                    'type': 'flow-logs',
                    'key': 'length(logs)',
                    'value': 0
                }
            ]
        })

        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['name'] == 'c7n-vnet-no-flowlog'

    def test_flow_log_filter_matching(self):
        p = self.load_policy({
            'name': 'test-azure-vnet',
            'resource': 'azure.vnet',
            'filters': [
                {'type': 'value', 'key': 'name', 'value': 'c7n-vnet'},
                {
                    'type': 'flow-logs',
                    'key': 'length(logs)',
                    'op': 'gt',
                    'value': 0
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_flow_log_filter_retention_below_90_days(self):
        p = self.load_policy({
            'name': 'test-azure-vnet',
            'resource': 'azure.vnet',
            'filters': [
                {'type': 'value', 'key': 'name', 'value': 'c7n-vnet'},
                {
                    'or': [
                        {
                            'type': 'flow-logs',
                            'key': 'logs',
                            'value': 'empty'
                        },
                        {
                            'and': [
                                {
                                    'type': 'flow-logs',
                                    'key': 'logs[0].retentionPolicy.days',
                                    'op': 'ne',
                                    'value': 0
                                },
                                {
                                    'type': 'flow-logs',
                                    'key': 'logs[0].retentionPolicy.days',
                                    'op': 'lt',
                                    'value': 90
                                }
                            ]
                        }
                    ]
                }
            ]
        })

        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['name'] == 'c7n-vnet'


class VnetSetFlowLogActionTest(BaseTest):

    def test_set_flow_log_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-vnet',
                'resource': 'azure.vnet',
                'actions': [
                    {
                        'type': 'set-flow-log',
                        'storage-account': (
                            '/subscriptions/%s'
                            '/resourceGroups/test_vnet/providers/Microsoft.Storage'
                            '/storageAccounts/cctestflowlogs' % DEFAULT_SUBSCRIPTION_ID
                        ),
                        'enabled': True,
                        'retention': 90
                    }
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_set_flow_log_requires_full_resource_id(self):
        with self.sign_out_patch():
            with self.assertRaises(PolicyValidationError):
                self.load_policy({
                    'name': 'test-azure-vnet',
                    'resource': 'azure.vnet',
                    'actions': [
                        {
                            'type': 'set-flow-log',
                            'storage-account': 'cctestflowlogs'
                        }
                    ]
                }, validate=True)

    def test_set_flow_log_requires_existing_flow_log(self):
        # No live calls needed: a vnet with no existing flow log fails before
        # the action ever touches the network client. This action only
        # updates an existing flow log; it does not create one.
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-vnet',
                'resource': 'azure.vnet',
                'actions': [{'type': 'set-flow-log', 'retention': 90}]
            }, validate=True)
            action = p.resource_manager.actions[0]
            resource = {
                'id': (
                    '/subscriptions/%s/resourceGroups/test_vnet'
                    '/providers/Microsoft.Network/virtualNetworks/c7n-vnet'
                    % DEFAULT_SUBSCRIPTION_ID
                ),
                'name': 'c7n-vnet',
                'location': 'southcentralus',
                'properties': {}
            }
            with self.assertRaises(PolicyExecutionError):
                action._process_resource(resource)

    @arm_template('vnet.json')
    def test_set_flow_log_updates_retention(self):
        # This test mutates its flow log, so it uses a dedicated vnet. The
        # c7n-vnet flow log must stay below 90 days for the retention filter test.
        vnet_name = 'c7n-vnet-set-flowlog'
        flow_log_name = 'c7n-vnet-set-flowlog-fl'

        session = Session()
        client = session.client('azure.mgmt.network.NetworkManagementClient')

        vnet = next(v for v in client.virtual_networks.list_all() if v.name == vnet_name)
        watcher = next(
            w for w in client.network_watchers.list_all()
            if w.location.lower() == vnet.location.lower()
        )
        watcher_rg = parse_resource_id(watcher.id)['resource_group']

        before = client.flow_logs.get(watcher_rg, watcher.name, flow_log_name)
        storage_id = before.storage_id
        original_days = before.retention_policy.days

        # The fixture enables Traffic Analytics and sets tags, neither of which
        # the action manages; they must survive the update.
        before_analytics = (
            before.flow_analytics_configuration.network_watcher_flow_analytics_configuration
        )
        assert before_analytics.enabled
        assert before.tags

        # Pick a target retention guaranteed to differ from whatever the fixture
        # currently has, so the action itself is the only thing that can produce
        # the observed change. Live re-runs against the same fixture (without
        # recreating it) leave the resource at whatever the previous run set it
        # to, so this can't assume a fixed starting value.
        target_days = 90 if original_days != 90 else 120

        # All three options are given so the update path that previously
        # skipped reading the existing flow log is the one exercised.
        p = self.load_policy({
            'name': 'test-azure-vnet',
            'resource': 'azure.vnet',
            'filters': [
                {'type': 'value', 'key': 'name', 'value': vnet_name}
            ],
            'actions': [
                {
                    'type': 'set-flow-log',
                    'storage-account': storage_id,
                    'enabled': True,
                    'retention': target_days
                }
            ]
        }, validate=True)

        resources = p.run()
        assert len(resources) == 1

        self.sleep_in_live_mode(30)

        after = client.flow_logs.get(watcher_rg, watcher.name, flow_log_name)
        assert after.enabled
        assert after.storage_id == storage_id
        assert after.retention_policy.days != original_days
        assert after.retention_policy.days == target_days

        after_analytics = (
            after.flow_analytics_configuration.network_watcher_flow_analytics_configuration
        )
        assert after_analytics.enabled
        assert after_analytics.workspace_resource_id == before_analytics.workspace_resource_id
        assert (after_analytics.traffic_analytics_interval
                == before_analytics.traffic_analytics_interval)
        assert after.tags == before.tags
