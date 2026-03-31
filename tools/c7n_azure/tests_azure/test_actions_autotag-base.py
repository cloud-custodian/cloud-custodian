# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy

from . import tools_tags as tools
from azure.mgmt.monitor.models import EventData
from .azure_common import BaseTest
from c7n.resources import load_resources
from c7n_azure.actions.tagging import AutoTagDate
from unittest.mock import Mock


class ActionsAutotagBaseTest(BaseTest):
    vm_id = "/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourcegroups/" \
            "TEST_VM/providers/Microsoft.Compute/virtualMachines/cctestvm"

    event_dict = {
        "caller": "cloud@custodian.com",
        "id": vm_id + "/events/37bf930a-fbb8-4c8c-9cc7-057cc1805c04/ticks/",
        "operationName": {
            "value": "Microsoft.Compute/virtualMachines/write",
            "localizedValue": "Create or Update Virtual Machine"
        },
        "eventTimestamp": "2019-05-01T15:20:04.8336028Z"
    }

    def __init__(self, *args, **kwargs):
        super(ActionsAutotagBaseTest, self).__init__(*args, **kwargs)

        self.events = []
        for i in range(5):
            event = EventData.from_dict(self.event_dict)
            event.id = event.id + str(i)
            self.events.append(event)
        load_resources(['azure.vm'])

    def test_get_first_element_resource(self):
        client_mock = Mock()
        client_mock.activity_logs.list.return_value = self.events

        manager = Mock()
        manager.type = 'vm'
        manager.get_client.return_value = client_mock

        resource = tools.get_resource({})
        base = AutoTagDate(data={'tag': 'test'}, manager=manager)
        base._prepare_processing()
        result = base._get_first_event(resource)

        client_mock.activity_logs.list.assert_called_once()
        self.assertEqual(result, self.events[-1])

    def test_get_first_element_resource_group(self):
        events = copy.copy(self.events)
        for e in events:
            e.operation_name.value = 'Microsoft.Resources/subscriptions/resourcegroups/write'

        client_mock = Mock()
        client_mock.activity_logs.list.return_value = events

        manager = Mock()
        manager.type = 'resourcegroup'
        manager.get_client.return_value = client_mock

        resource_group = tools.get_resource_group_resource({})
        base = AutoTagDate(data={'tag': 'test'}, manager=manager)
        base._prepare_processing()
        result = base._get_first_event(resource_group)

        client_mock.activity_logs.list.assert_called_once()
        self.assertEqual(result, self.events[-1])
