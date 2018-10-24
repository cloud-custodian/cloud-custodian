# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from azure_common import BaseTest, arm_template
from c7n_azure.azure_events import AzureEvents, AzureEventSubscription
from azure.mgmt.eventgrid.models import StorageQueueEventSubscriptionDestination
from c7n_azure.storage_utils import StorageUtilities


class AzureEventSubscriptionsTest(BaseTest):
    def setUp(self):
        super(AzureEventSubscriptionsTest, self).setUp()

    @arm_template('storage.json')
    def test_create_azure_event_subscription(self):
        account = self.setup_account()
        queue_name = 'cctestevensub'
        StorageUtilities.create_queue_from_storage_account(account, queue_name)
        sub_destination = StorageQueueEventSubscriptionDestination(resource_id=account.id,
                                                                   queue_name=queue_name)
        sub_name = 'custodiantestsubscription'
        event_subscription = AzureEventSubscription.create(sub_destination, sub_name)
        self.assertEqual(event_subscription.name, sub_name)
        self.assertEqual(event_subscription.destination.endpoint_type, 'StorageQueue')
