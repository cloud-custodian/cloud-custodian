# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from azure.mgmt.monitor.models import EventData
from c7n_azure.actions.tagging import AutoTagBase, AutoTagUser
from unittest.mock import patch, Mock

from c7n.exceptions import PolicyValidationError
from c7n.filters import FilterValidationError
from c7n.resources import load_resources
from . import tools_tags as tools
from .azure_common import BaseTest


class ActionsAutotagUserTest(BaseTest):

    existing_tags = {'pre-existing-1': 'unmodified', 'pre-existing-2': 'unmodified'}

    vm_id = "/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourcegroups/" \
            "TEST_VM/providers/Microsoft.Compute/virtualMachines/cctestvm"

    first_event = EventData.from_dict({
        "caller": "cloud_caller@custodian.com",
        "id": vm_id + "/events/37bf930a-fbb8-4c8c-9cc7-057cc1805c04/ticks/636923208048336028",
        "operationName": {
            "value": "Microsoft.Compute/virtualMachines/write",
            "localizedValue": "Create or Update Virtual Machine"
        },
        "claims": {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": "cloud_n@custodian.com",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn": "cloud@custodian.com"
        },
        "eventTimestamp": "2019-05-01T15:20:04.8336028Z"
    })

    def __init__(self, *args, **kwargs):
        super(ActionsAutotagUserTest, self).__init__(*args, **kwargs)
        load_resources(['azure.vm'])

    def _get_action(self, data):
        return AutoTagUser(data=data, manager=Mock())

    def test_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                tools.get_policy([
                    {'type': 'auto-tag-user',
                     'tag': 'user'},
                ]),
                validate=True))

        with self.assertRaises(FilterValidationError):
            # Days should be in 1-90 range
            self.load_policy(tools.get_policy([
                {'type': 'auto-tag-user',
                 'tag': 'CreatorEmail',
                 'days': 91}
            ]), validate=True)

        with self.assertRaises(FilterValidationError):
            # Days should be in 1-90 range
            self.load_policy(tools.get_policy([
                {'type': 'auto-tag-user',
                 'tag': 'CreatorEmail',
                 'days': 0}
            ]), validate=True)

        with self.assertRaises(PolicyValidationError):
            # Event grid mode is incompatible with days
            self.load_policy(tools.get_policy_event_grid([
                {'type': 'auto-tag-user',
                 'tag': 'CreatorEmail',
                 'days': 40}
            ]), validate=True)

    @patch.object(AutoTagBase, '_get_first_event', return_value=first_event)
    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_auto_tag_add_creator_tag(self, update_resource_tags, _2):
        """Adds CreatorEmail to a resource group."""

        action = self._get_action({'tag': 'CreatorEmail', 'days': 10, 'update': True})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        tags = tools.get_tags_parameter(update_resource_tags)

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'CreatorEmail': 'cloud@custodian.com'})

        self.assertEqual(tags, expected_tags)

    @patch.object(AutoTagBase, '_get_first_event', return_value=first_event)
    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_auto_tag_update_false_noop_for_existing_tag(self, update_resource_tags, _2):
        """Adds CreatorEmail to a resource group"""

        action = self._get_action({'tag': 'CreatorEmail', 'days': 10, 'update': False})

        tags = self.existing_tags.copy()
        tags.update({'CreatorEmail': 'do-not-modify'})
        resource = tools.get_resource(tags)

        action.process([resource])

        update_resource_tags.assert_not_called()

    def test_auto_tag_user_event_grid_user_event(self):
        event = self._get_event(evidence={'principalType': 'User'},
                                claims={
                                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn':
                                        'cloud@custodian.com', })
        self._test_event(event, 'cloud@custodian.com')

    def test_auto_tag_user_event_grid_service_admin_event(self):
        event = self._get_event(
            evidence={'role': 'Subscription Admin'},
            claims={
                'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress':
                    'cloud@custodian.com', })
        self._test_event(event, 'cloud@custodian.com')

    def test_auto_tag_user_event_grid_sp_event(self):
        event = self._get_event(evidence={'principalType': 'ServicePrincipal'},
                                claims={'appid': '12345'})
        self._test_event(event, '12345')

    def test_auto_tag_user_event_grid_group_event(self):
        # TODO: REVIEW
        event = self._get_event(evidence={'principalType': 'User'},
                                claims={
                                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn':
                                        'cloud@custodian.com'})
        self._test_event(event, 'cloud@custodian.com')

    def test_auto_tag_user_event_grid_default_to_upn(self):
        event = self._get_event(evidence={'principalType': 'DoesNotMatter'},
                                claims={
                                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn':
                                        'cloud@custodian.com',
                                    'claim1': 'myemail@contoso.com'})
        self._test_event(event, 'cloud@custodian.com')

    def test_auto_tag_user_event_grid_name(self):
        event = self._get_event(evidence={'principalType': 'DoesNotMatter'},
                                claims={
                                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn':
                                        'cloud@custodian.com',
                                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name':
                                        'name@custodian.com',
                                    'claim1': 'myemail@contoso.com'})
        self._test_event(event, 'name@custodian.com', default_claim='name')

    def test_auto_tag_user_event_grid_missing_upn(self):
        event = self._get_event(evidence={'principalType': 'DoesNotMatter'},
                                claims={
                                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name':
                                        'name@custodian.com',
                                    'claim1': 'myemail@contoso.com'})
        self._test_event(event, 'name@custodian.com', default_claim='upn')

    def test_auto_tag_user_event_grid_missing_name(self):
        event = self._get_event(evidence={'principalType': 'DoesNotMatter'},
                                claims={
                                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn':
                                        'cloud@custodian.com',
                                    'claim1': 'myemail@contoso.com'})
        self._test_event(event, 'cloud@custodian.com', default_claim='name')

    def test_auto_tag_user_event_grid_find_email_in_claims(self):
        event = self._get_event(evidence={'principalType': 'DoesNotMatter'},
                                claims={'claim1': 'notEmailAddress',
                                        'claim2': 'cloud@custodian.com'
                                        })
        self._test_event(event, 'cloud@custodian.com')

    def test_auto_tag_user_event_grid_unknown_principal_event(self):
        event = self._get_event(evidence={'principalType': 'Group'},
                                claims={})
        self._test_event(event, 'Unknown')

    def test_auto_tag_user_event_grid_user_event_missing_info(self):
        event = self._get_event(evidence={'principalType': 'User'},
                                claims={})
        self._test_event(event, 'Unknown')

    def test_auto_tag_user_event_grid_sp_event_missing_info(self):
        event = self._get_event(evidence={'principalType': 'ServicePrincipal'},
                                claims={})
        self._test_event(event, 'Unknown')

    def _get_event(self, evidence, claims):
        return {
            'subject': self.vm_id,
            'data': {
                'authorization': {
                    'evidence': evidence
                },
                'claims': claims,
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def _test_event(self, event, expected_tag_value, update_resource_tags, default_claim='upn'):
        action = self._get_action({'tag': 'CreatorEmail',
                                   'update': True,
                                   'default-claim': default_claim})

        resource = tools.get_resource(self.existing_tags)
        action.process(resources=[resource], event=event)

        tags = tools.get_tags_parameter(update_resource_tags)

        expected_tags = self.existing_tags.copy()
        expected_tags.update({'CreatorEmail': expected_tag_value})

        self.assertEqual(tags, expected_tags)
