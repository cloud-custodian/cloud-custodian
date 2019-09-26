# Copyright 2019 Microsoft Corporation
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

from azure_common import BaseTest
from c7n_azure.actions.base import AzureBaseAction, AzureEventAction
from c7n_azure.session import Session
from mock import patch, MagicMock, ANY

from c7n.utils import local_session


class AzureBaseActionTest(BaseTest):
    def test_return_success(self):
        action = AzureBaseActionTest._get_action()
        action.process([{'id': '1'}, {'id': '2'}], None)

        self.assertEqual(2, action.log.info.call_count)

        action.log.info.assert_any_call(
            ANY,
            extra={'properties': {'resource_id': '1', 'action': 'TestAction'}})

        action.log.info.assert_any_call(
            ANY,
            extra={'properties': {'resource_id': '2', 'action': 'TestAction'}})

    def test_return_success_message(self):
        action = AzureBaseActionTest._get_action()
        action.process([
            {'id': '1', 'name': 'one', 'message': 'foo'},
            {'id': '2', 'name': 'two', 'message': 'bar'}],
            None)

        self.assertEqual(2, action.log.info.call_count)

        action.log.info.assert_any_call(
            "Resource 'one' Modified by TestAction. foo",
            extra={'properties': {'resource_id': '1', 'action': 'TestAction'}})

        action.log.info.assert_any_call(
            "Resource 'two' Modified by TestAction. bar",
            extra={'properties': {'resource_id': '2', 'action': 'TestAction'}})

    @patch('sys.modules', return_value=[])
    def test_resource_failed(self, _):
        action = AzureBaseActionTest._get_action()
        action.process([
            {'id': '1', 'exception': Exception('foo'), 'name': 'bar', 'type': 'vm'},
            {'id': '2'}],
            None)

        action.log.exception.assert_called_once_with(
            ANY,
            extra={'properties': {'resource_id': '1', 'action': 'TestAction'}})

        action.log.info.assert_called_once_with(
            ANY,
            extra={'properties': {'resource_id': '2', 'action': 'TestAction'}})

    @patch('sys.modules', return_value=[])
    def test_resource_failed_event(self, _):
        action = AzureBaseActionTest._get_event_action()
        action.process([
            {'id': '1', 'exception': Exception('foo'), 'name': 'bar', 'type': 'vm'},
            {'id': '2'}],
            None)

        action.log.exception.assert_called_once_with(
            ANY,
            extra={'properties': {'resource_id': '1', 'action': 'TestEventAction'}})

        action.log.info.assert_called_once_with(
            ANY,
            extra={'properties': {'resource_id': '2', 'action': 'TestEventAction'}})

    @staticmethod
    def _get_action():
        action = TestAction()
        action.client = MagicMock()
        action.manager = MagicMock()
        action.log.info = MagicMock()
        action.log.exception = MagicMock()
        action.session = local_session(Session)
        return action

    @staticmethod
    def _get_event_action():
        action = TestEventAction()
        action.client = MagicMock()
        action.manager = MagicMock()
        action.log.info = MagicMock()
        action.log.exception = MagicMock()
        action.session = local_session(Session)
        return action


class TestAction(AzureBaseAction):
    def _process_resource(self, resource):
        exception = resource.get('exception')
        if exception:
            raise exception

        message = resource.get('message')
        if message:
            return message


class TestEventAction(AzureEventAction):
    def _process_resource(self, resource, event):
        exception = resource.get('exception')
        if exception:
            raise exception

        message = resource.get('message')
        if message:
            return message
