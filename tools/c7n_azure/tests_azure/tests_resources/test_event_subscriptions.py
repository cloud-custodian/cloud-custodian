# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from azure.mgmt.eventgrid.models import \
    StorageQueueEventSubscriptionDestination
from c7n_azure.azure_events import AzureEventSubscription
from c7n_azure.storage_utils import StorageUtilities

from ..azure_common import BaseTest, arm_template


class AzureEventSubscriptionsTest(BaseTest):
    event_sub_name = 'custodiantestsubscription'

    def setUp(self):
        super(AzureEventSubscriptionsTest, self).setUp()
        account = self.setup_account()
        queue_name = 'cctesteventsub'
        StorageUtilities.create_queue_from_storage_account(account, queue_name, self.session)
        event_sub_destination = StorageQueueEventSubscriptionDestination(
            resource_id=account.id, queue_name=queue_name)
        AzureEventSubscription.create(event_sub_destination,
                                      self.event_sub_name,
                                      self.session.get_subscription_id(),
                                      session=self.session)

    def test_event_subscription_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-event-subscription',
                'resource': 'azure.eventsubscription',
                'actions': [
                    {'type': 'delete'}
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('storage.json')
    def test_azure_event_subscription_policy_run(self):
        p = self.load_policy({
            'name': 'test-azure-event-subscriptions',
            'resource': 'azure.eventsubscription',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': self.event_sub_name}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('storage.json')
    def test_azure_event_subscription_delete(self):
        p_get = self.load_policy({
            'name': 'test-azure-event-subscriptions',
            'resource': 'azure.eventsubscription',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': self.event_sub_name}],
        })
        resources_pre_delete = p_get.run()
        self.assertEqual(len(resources_pre_delete), 1)

        p_delete = self.load_policy({
            'name': 'test-azure-event-subscriptions',
            'resource': 'azure.eventsubscription',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': self.event_sub_name}],
            'actions': [
                {'type': 'delete'}
            ]
        }, validate=True)

        p_delete.run()
        self.sleep_in_live_mode(5)
        resources_post_delete = p_get.run()
        self.assertEqual(len(resources_post_delete), 0)
