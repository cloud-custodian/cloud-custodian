# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError
from c7n.exceptions import PolicyValidationError
from c7n.actions import Action, ActionRegistry
from .common import BaseTest


class ActionTest(BaseTest):

    def test_process_unimplemented(self):
        self.assertRaises(NotImplementedError, Action().process, None)

    def test_filter_resources(self):
        a = Action()
        a.type = 'set-x'
        log_output = self.capture_logging('custodian.actions')
        resources = [
            {'app': 'X', 'state': {'status': 'running'}},
            {'app': 'Y', 'state': {'status': 'stopped'}},
            {'app': 'Z', 'state': {'status': 'running'}}]
        assert {'X', 'Z'} == {r['app'] for r in a.filter_resources(
            resources, 'state.status', ('running',))}
        assert log_output.getvalue().strip() == (
            'set-x implicitly filtered 2 of 3 resources key:state.status on running')

    def test_run_api(self):
        resp = {
            "Error": {"Code": "DryRunOperation", "Message": "would have succeeded"},
            "ResponseMetadata": {"HTTPStatusCode": 412},
        }

        func = lambda: (_ for _ in ()).throw(ClientError(resp, "test"))  # NOQA
        # Hard to test for something because it just logs a message, but make
        # sure that the ClientError gets caught and not re-raised
        Action()._run_api(func)

    def test_run_api_error(self):
        resp = {"Error": {"Code": "Foo", "Message": "Bar"}}
        func = lambda: (_ for _ in ()).throw(ClientError(resp, "test2"))  # NOQA
        self.assertRaises(ClientError, Action()._run_api, func)


class ActionRegistryTest(BaseTest):

    def test_error_bad_action_type(self):
        self.assertRaises(
            PolicyValidationError, ActionRegistry("test.actions").factory, {}, None)

    def test_error_unregistered_action_type(self):
        self.assertRaises(
            PolicyValidationError, ActionRegistry("test.actions").factory, "foo", None
        )
