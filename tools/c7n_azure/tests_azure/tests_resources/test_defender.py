# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import HttpResponseError
from azure.mgmt.security.models import Extension, Pricing

from c7n.exceptions import PolicyValidationError

from ..azure_common import BaseTest, strict_cassette


class DefenderTest(BaseTest):
    def test_azure_defender_pricing(self):
        p = self.load_policy(
            {
                "name": "test-azure-defender-pricing",
                "resource": "azure.defender-pricing",
                "filters": [
                    {"name": "KeyVaults"},
                ],
            }
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_azure_defender_setting(self):
        p = self.load_policy(
            {
                "name": "test-azure-defender-setting",
                "resource": "azure.defender-setting",
                "filters": [
                    {"name": "MCAS"},
                    {"kind": "DataExportSettings"},
                    {"properties.enabled": True},
                ],
            }
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_azure_defender_autoprovisioning(self):
        p = self.load_policy(
            {
                "name": "test-azure-defender-autoprovisioning",
                "resource": "azure.defender-autoprovisioning",
                "filters": [
                    {"name": "default"},
                    {"properties.autoProvision": "On"},
                ],
            }
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_azure_defender_assessments(self):
        p = self.load_policy({
            'name': 'test-security-assessments',
            'resource': 'azure.defender-assessment',
            'filters': [{
                'type': 'value',
                'key': 'properties.status.code',
                'op': 'eq',
                'value': 'Healthy'}]})
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], '2a548cf9-6de3-491e-b24a-cf277fe36d4d')

    def test_azure_defender_contacts(self):
        p = self.load_policy({
            'name': 'test-security-contact',
            'resource': 'azure.defender-contact'
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('azurebilling@epmcseclab.com', resources[0]['properties']['emails'])

    def test_azure_defender_contacts_validate_schemas(self):
        p = self.load_policy({
            'name': 'test-security-contacts-schema-validate',
            'resource': 'azure.defender-contact',
        }, validate=True)
        self.assertTrue(p)

    def test_azure_defender_jit_policies_query(self):
        p = self.load_policy({
            'name': 'test-security-jit-policy',
            'resource': 'azure.defender-jit-policy',
        })
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'VVvm1')

    def test_azure_defender_jit_policies_filter(self):
        p = self.load_policy({
            'name': 'test-security-jit-policy-filter',
            'resource': 'azure.defender-jit-policy',
            'filters': [{
                'type': 'value',
                'key': 'properties.virtualMachines[].ports[].number',
                'op': 'contains',
                'value': 22,
            }, {
                'type': 'list-item',
                'key': 'properties.virtualMachines[]',
                'attrs': [{
                    'type': 'value',
                    'key': 'id',
                    'op': 'regex',
                    'value': r'\/.+\/virtualMachines\/.+',
                }],
            }]})
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'VVvm1')


# The recorded tests require their plan (KeyVaults, VirtualMachines) to start
# on the Free tier. Free is the simplest state: it has no sub-plan or
# extensions, so turning the plan on and back off leaves it exactly as it was.
# Starting from Standard, the round trip can lose a sub-plan or extensions the
# test doesn't know to put back.
#
# If assert_starts_free fails while recording, the plan is on Standard. Either
# set it to Free first (az security pricing create -n <plan> --tier free), or
# point the test at another plan that's already Free (find one with
# az security pricing list -o table). Changing the plan means re-recording the
# test, and the sub-plan test also needs a plan with more than one sub-plan.
class DefenderPricingSetTierTest(BaseTest):
    def test_set_pricing_tier_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-defender-set-pricing-tier',
                'resource': 'azure.defender-pricing',
                'actions': [{
                    'type': 'set-pricing-tier',
                    'pricing-tier': 'Standard',
                    'sub-plan': 'PerTransaction',
                    'enforce': False,
                    'extensions': [{'name': 'OnUploadMalwareScanning', 'isEnabled': True}],
                }],
            }, validate=True)
            assert p

    def test_set_pricing_tier_schema_invalid_tier(self):
        with self.sign_out_patch():
            with pytest.raises(PolicyValidationError):
                self.load_policy({
                    'name': 'test-defender-set-pricing-tier',
                    'resource': 'azure.defender-pricing',
                    'actions': [{'type': 'set-pricing-tier', 'pricing-tier': 'Premium'}],
                }, validate=True)

    def test_set_pricing_tier_free_rejects_sub_plan(self):
        with self.sign_out_patch():
            with pytest.raises(PolicyValidationError):
                self.load_policy({
                    'name': 'test-defender-set-pricing-tier',
                    'resource': 'azure.defender-pricing',
                    'actions': [{
                        'type': 'set-pricing-tier',
                        'pricing-tier': 'Free',
                        'sub-plan': 'P1',
                    }],
                }, validate=True)

    def run_set_pricing_tier(self, plan, match, action):
        """Run set-pricing-tier on ``plan``, which the ``match`` filter must
        select. Each step's filter checks the state the previous step left.
        """
        p = self.load_policy({
            'name': 'test-defender-set-pricing-tier',
            'resource': 'azure.defender-pricing',
            'filters': [{'name': plan}, match],
            'actions': [action],
        })
        assert [r['name'] for r in p.run()] == [plan]

    def get_pricing(self, plan):
        resources = self.load_policy({
            'name': 'test-defender-pricing',
            'resource': 'azure.defender-pricing',
            'filters': [{'name': plan}],
        }).run()
        assert len(resources) == 1
        return resources[0]['properties']

    def assert_starts_free(self, plan):
        assert self.get_pricing(plan)['pricingTier'] == 'Free', \
            f'record with the {plan} plan on Free'

    def assert_ends_free(self, plan):
        pricing = self.get_pricing(plan)
        assert pricing['pricingTier'] == 'Free'
        assert 'subPlan' not in pricing
        assert 'extensions' not in pricing

    @strict_cassette('set-pricing-tier-keyvaults')
    def test_set_pricing_tier(self):
        # Pricings belong to the subscription, so there is no ARM template.
        # Record with the KeyVaults plan on Free: the test turns it on, then
        # back off. Recording bills Defender for Key Vaults while it runs.
        self.assert_starts_free('KeyVaults')

        self.run_set_pricing_tier(
            'KeyVaults', {'properties.pricingTier': 'Free'},
            {'type': 'set-pricing-tier', 'pricing-tier': 'Standard'})
        self.run_set_pricing_tier(
            'KeyVaults', {'properties.pricingTier': 'Standard'},
            {'type': 'set-pricing-tier', 'pricing-tier': 'Free'})
        self.assert_ends_free('KeyVaults')

    @strict_cassette('set-pricing-tier-sub-plan')
    def test_set_pricing_tier_sub_plan(self):
        # Record with the VirtualMachines plan on Free: the test sets Standard
        # with sub-plan P1, sets Standard again without a sub-plan, then sets
        # Free. Recording bills Defender for Servers (per server) while it
        # runs.
        self.assert_starts_free('VirtualMachines')

        self.run_set_pricing_tier(
            'VirtualMachines', {'properties.pricingTier': 'Free'},
            {'type': 'set-pricing-tier', 'pricing-tier': 'Standard', 'sub-plan': 'P1'})
        self.run_set_pricing_tier(
            'VirtualMachines', {'properties.subPlan': 'P1'},
            {'type': 'set-pricing-tier', 'pricing-tier': 'Standard'})
        self.run_set_pricing_tier(
            'VirtualMachines', {'properties.subPlan': 'P1'},
            {'type': 'set-pricing-tier', 'pricing-tier': 'Free'})
        self.assert_ends_free('VirtualMachines')

    def process_with_mock_client(self, action_data, current):
        """Run the action on the VirtualMachines plan against a mocked client
        whose plan is ``current``, and return the Pricing it sent to update.

        Cassettes don't keep request bodies, so mocked tests check them.
        """
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-defender-set-pricing-tier',
                'resource': 'azure.defender-pricing',
                'actions': [dict(action_data, type='set-pricing-tier')],
            }, validate=True)
        action = p.resource_manager.actions[0]
        action.client = MagicMock()
        action.scope_id = 'subscriptions/00000000-0000-0000-0000-000000000000'
        action.client.pricings.get.return_value = current

        action._process_resource({'name': 'VirtualMachines'})

        _, name, sent = action.client.pricings.update.call_args.args
        assert name == 'VirtualMachines'
        return sent

    def test_set_pricing_tier_merges_extensions(self):
        sent = self.process_with_mock_client(
            {
                'pricing-tier': 'Standard',
                'enforce': True,
                'extensions': [
                    {'name': 'AgentlessVmScanning', 'isEnabled': False},
                    {'name': 'FileIntegrityMonitoring', 'isEnabled': True,
                     'additionalExtensionProperties': {'DefinedWorkspaceId': 'ws'}},
                ],
            },
            Pricing(
                pricing_tier='Standard',
                sub_plan='P2',
                extensions=[
                    Extension(name='MdeDesignatedSubscription', is_enabled='False'),
                    Extension(name='AgentlessVmScanning', is_enabled='True',
                              additional_extension_properties={'ExclusionTags': '[]'}),
                ],
            ),
        )
        assert sent.pricing_tier == 'Standard'
        assert sent.enforce == 'True'
        assert sent.sub_plan == 'P2'
        # Named extensions are updated or added; the plan's others are kept
        assert {e.name: (e.is_enabled, e.additional_extension_properties)
                for e in sent.extensions} == {
            'MdeDesignatedSubscription': ('False', None),
            'AgentlessVmScanning': ('False', {'ExclusionTags': '[]'}),
            'FileIntegrityMonitoring': ('True', {'DefinedWorkspaceId': 'ws'}),
        }

    def test_set_pricing_tier_free_clears_sub_plan_and_extensions(self):
        sent = self.process_with_mock_client(
            {'pricing-tier': 'Free'},
            Pricing(
                pricing_tier='Standard',
                sub_plan='P1',
                extensions=[Extension(name='MdeDesignatedSubscription', is_enabled='False')],
            ),
        )
        # Azure rejects a sub-plan or extensions on Free
        assert (sent.pricing_tier, sent.sub_plan, sent.extensions) == ('Free', None, None)

    def test_set_pricing_tier_raises_after_batch(self):
        # The base class would swallow the error outside pytest and report success
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-defender-set-pricing-tier',
                'resource': 'azure.defender-pricing',
                'actions': [{'type': 'set-pricing-tier', 'pricing-tier': 'Standard'}],
            }, validate=True)
        action = p.resource_manager.actions[0]
        action.client = MagicMock()
        action.scope_id = 'subscriptions/00000000-0000-0000-0000-000000000000'
        action.client.pricings.update.side_effect = [
            HttpResponseError('Plan update failed'), MagicMock()]

        with patch.object(action, '_prepare_processing'):
            with pytest.raises(HttpResponseError, match='Plan update failed'):
                action.process([{'name': 'KeyVaults'}, {'name': 'VirtualMachines'}])

        assert [c.args[1] for c in action.client.pricings.update.call_args_list] == [
            'KeyVaults', 'VirtualMachines']
