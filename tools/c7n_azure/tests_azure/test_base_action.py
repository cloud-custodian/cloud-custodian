# Copyright 2019 Microsoft Corporation
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import BaseTest
from c7n_azure.actions.base import AzureBaseAction, AzureEventAction
from c7n_azure.session import Session
from mock import patch, MagicMock, ANY

from c7n.utils import local_session


class AzureBaseActionTest(BaseTest):
    def test_return_success(self):
        action = SampleAction()
        action.process([{'id': '1'}, {'id': '2'}], None)

        self.assertEqual(2, action.log.info.call_count)

        action.log.info.assert_any_call(
            ANY,
            extra={'properties': {'resource_id': '1', 'action': 'test'}})

        action.log.info.assert_any_call(
            ANY,
            extra={'properties': {'resource_id': '2', 'action': 'test'}})

    def test_return_success_message(self):
        action = SampleAction()
        action.process([
            {'id': '1', 'name': 'one', 'message': 'foo', 'resourceGroup': 'rg'},
            {'id': '2', 'name': 'two', 'message': 'bar'}],
            None)

        self.assertEqual(2, action.log.info.call_count)

        action.log.info.assert_any_call(
            "Action 'test' modified 'one' in resource group 'rg'. foo",
            extra={'properties': {'resource_id': '1', 'action': 'test'}})

        action.log.info.assert_any_call(
            "Action 'test' modified 'two' in resource group 'unknown'. bar",
            extra={'properties': {'resource_id': '2', 'action': 'test'}})

    @patch('sys.modules', return_value=[])
    def test_resource_failed(self, _):
        action = SampleAction()
        action.process([
            {'id': '1', 'exception': Exception('foo'), 'name': 'bar', 'type': 'vm'},
            {'id': '2'}],
            None)

        action.log.exception.assert_called_once_with(
            ANY,
            extra={'properties': {'resource_id': '1', 'action': 'test'}})

        action.log.info.assert_called_once_with(
            ANY,
            extra={'properties': {'resource_id': '2', 'action': 'test'}})

    @patch('sys.modules', return_value=[])
    def test_resource_failed_event(self, _):
        action = SampleEventAction()
        action.process([
            {'id': '1', 'exception': Exception('foo'), 'name': 'bar', 'type': 'vm'},
            {'id': '2'}],
            None)

        action.log.exception.assert_called_once_with(
            ANY,
            extra={'properties': {'resource_id': '1', 'action': 'test'}})

        action.log.info.assert_called_once_with(
            ANY,
            extra={'properties': {'resource_id': '2', 'action': 'test'}})


class SampleAction(AzureBaseAction):

    def __init__(self):
        self.client = MagicMock()
        self.manager = MagicMock()
        self.log.info = MagicMock()
        self.log.exception = MagicMock()
        self.session = local_session(Session)
        self.type = "test"

    def _process_resource(self, resource):
        exception = resource.get('exception')
        if exception:
            raise exception

        message = resource.get('message')
        if message:
            return message


class SampleEventAction(AzureEventAction):

    def __init__(self):
        self.client = MagicMock()
        self.manager = MagicMock()
        self.log.info = MagicMock()
        self.log.exception = MagicMock()
        self.session = local_session(Session)
        self.type = "test"

    def _process_resource(self, resource, event):
        exception = resource.get('exception')
        if exception:
            raise exception

        message = resource.get('message')
        if message:
            return message
