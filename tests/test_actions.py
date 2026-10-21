# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import io
from unittest import mock

from botocore.exceptions import ClientError
from c7n.exceptions import PolicyValidationError
from c7n.actions import Action, ActionRegistry
from .common import BaseTest


class InvokeLambdaTest(BaseTest):
    # https://github.com/cloud-custodian/cloud-custodian/issues/10965
    # a qualifier on invoke-lambda raised KeyError: 'Qualifier'

    def _invoke(self, action):
        mock_factory = mock.MagicMock()
        mock_factory.region = 'us-east-1'
        client = mock_factory().client('lambda')
        client.invoke.return_value = {'Payload': io.BytesIO(b'{}')}
        p = self.load_policy(
            {'name': 'invoke', 'resource': 's3',
             'actions': [dict(action, type='invoke-lambda', function='my-func')]},
            session_factory=mock_factory)
        with mock.patch('c7n.utils.get_account_alias_from_sts', return_value='alias'):
            p.resource_manager.actions[0].process([{'Name': 'bucket'}])
        return client.invoke

    def test_invoke_lambda_qualifier(self):
        invoke = self._invoke({'qualifier': 'prod'})
        invoke.assert_called_once()
        self.assertEqual(invoke.call_args.kwargs['FunctionName'], 'my-func')
        self.assertEqual(invoke.call_args.kwargs['Qualifier'], 'prod')

    def test_invoke_lambda_no_qualifier(self):
        invoke = self._invoke({})
        invoke.assert_called_once()
        self.assertNotIn('Qualifier', invoke.call_args.kwargs)


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
