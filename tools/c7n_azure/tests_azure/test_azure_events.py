# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from azure.mgmt.eventgrid.models import StorageQueueEventSubscriptionDestination
from .azure_common import BaseTest
from c7n_azure.azure_events import AzureEvents, AzureEventSubscription
from c7n_azure.session import Session
from mock import patch


class AzureEventsTest(BaseTest):
    def setUp(self):
        super(AzureEventsTest, self).setUp()
        self.session = Session()

    def test_get_returns_event_dict(self):
        event_dic = AzureEvents.get('VmWrite')
        self.assertEqual(event_dic['event'], 'write')
        self.assertEqual(event_dic['resource_provider'], 'Microsoft.Compute/virtualMachines')

    def test_get_event_operations_one_string(self):
        event_string = 'VmWrite'
        event_operations = AzureEvents.get_event_operations([event_string])
        self.assertEqual(len(event_operations), 1)
        self.assertEqual(event_operations[0], 'Microsoft.Compute/virtualMachines/write')

    def test_get_event_operations_one_event_object(self):
        event_dictionary = {
            'resourceProvider': 'Microsoft.Compute/virtualMachines',
            'event': 'write'
        }
        event_operations = AzureEvents.get_event_operations([event_dictionary])
        self.assertEqual(len(event_operations), 1)
        self.assertEqual(event_operations[0], 'Microsoft.Compute/virtualMachines/write')

    def test_get_event_operations_both_event_types(self):
        event_string = 'AppServicePlanWrite'
        event_dict = {
            'resourceProvider': 'Microsoft.Compute/virtualMachines',
            'event': 'write'
        }
        event_operations = AzureEvents.get_event_operations([event_string, event_dict])
        self.assertEqual(len(event_operations), 2)
        self.assertTrue('Microsoft.Compute/virtualMachines/write' in event_operations)
        self.assertTrue('Microsoft.Web/serverFarms/write' in event_operations)

    @patch('azure.mgmt.eventgrid.operations.''EventSubscriptionsOperations.begin_create_or_update')
    def test_create_azure_event_subscription(self, create_mock):
        sub_destination = StorageQueueEventSubscriptionDestination(resource_id="cctestid",
                                                                   queue_name="cctestevensub")
        sub_name = 'custodiantestsubscription'
        sub_id = self.session.get_subscription_id()
        AzureEventSubscription.create(sub_destination, sub_name, sub_id)

        args = create_mock.mock_calls[0].args
        self.assertTrue(sub_id in args[0])
        self.assertEqual(sub_name, args[1])
        self.assertEqual(sub_destination, args[2].destination)
