# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from unittest import mock

from botocore.exceptions import ClientError

from .apicallcaptor import ApiCallCaptor
from .common import BaseTest
from c7n.exceptions import PolicyExecutionError
from c7n.executor import MainThreadExecutor
from c7n.resources.awslambda import (
    DeleteWebFunction,
    LambdaWebEndpoint,
    LambdaWebFunction,
    WebEndpointCrossAccount,
    WebFunctionCrossAccount,
    WebFunctionEndpointFilter,
    _endpoint_statement_applies,
    parse_endpoint_arn,
)

ACCOUNT = '644160558196'
FUNCTION_ARN = 'arn:aws:lambda:us-east-1:%s:web-function/scoped-api' % ACCOUNT

# The Web Function flight data under tests/data/placebo/test_lambda_web_* is
# hand written from the lambda-web service model, not recorded.


class LambdaWebTest(BaseTest):

    def setUp(self):
        super().setUp()
        # keep placebo call ordering deterministic
        for cls in (LambdaWebFunction, WebFunctionEndpointFilter,
                    WebFunctionCrossAccount, WebEndpointCrossAccount,
                    LambdaWebEndpoint, DeleteWebFunction):
            self.patch(cls, 'executor_factory', MainThreadExecutor)

    def load(self, name, resource, filters=None, actions=None, **kw):
        factory = self.replay_flight_data(name)
        p = self.load_policy(
            {'name': name.replace('_', '-'), 'resource': resource,
             'filters': filters or [], 'actions': actions or []},
            session_factory=factory, **kw)
        return p, factory


class LambdaWebFunctionTest(LambdaWebTest):

    def test_query(self):
        p, _ = self.load('test_lambda_web_function_query', 'aws.lambda-web-function')
        resources = p.run()
        self.assertEqual(
            [r['functionName'] for r in resources],
            ['public-api', 'partner-api', 'scoped-api'])
        self.assertEqual(resources[0]['Tags'], [{'Key': 'owner', 'Value': 'team-a'}])
        self.assertEqual(resources[2]['Tags'], [])
        self.assertEqual(
            p.resource_manager.get_arns(resources)[0],
            'arn:aws:lambda:us-east-1:%s:web-function/public-api' % ACCOUNT)

    def test_get_resources(self):
        p, _ = self.load('test_lambda_web_function_get_resources', 'aws.lambda-web-function')
        resources = p.resource_manager.get_resources(['public-api', 'missing'])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['functionName'], 'public-api')
        self.assertEqual(resources[0]['Tags'], [{'Key': 'owner', 'Value': 'team-a'}])

    def test_endpoint_filter(self):
        p, _ = self.load(
            'test_lambda_web_function_endpoint_filter', 'aws.lambda-web-function',
            filters=[{'type': 'endpoint', 'key': 'authType', 'value': 'ApplicationManaged'}])
        resources = p.run()
        self.assertEqual([r['functionName'] for r in resources], ['public-api'])
        self.assertEqual(len(resources[0]['c7n:Endpoints']), 2)

    def test_cross_account(self):
        p, _ = self.load(
            'test_lambda_web_function_cross_account', 'aws.lambda-web-function',
            filters=[{'type': 'cross-account'}])
        resources = p.run()
        self.assertEqual(
            [r['functionName'] for r in resources], ['partner-api', 'scoped-api'])
        violations = resources[1]['CrossAccountViolations']
        self.assertEqual([v['Sid'] for v in violations], ['ExternalA'])

    def test_cross_account_whitelist(self):
        p, _ = self.load(
            'test_lambda_web_function_cross_account', 'aws.lambda-web-function',
            filters=[{'type': 'cross-account', 'whitelist': ['222233334444']}])
        self.assertEqual(
            [r['functionName'] for r in p.run()], ['scoped-api'])

    def test_tag(self):
        p, factory = self.load(
            'test_lambda_web_function_tag', 'aws.lambda-web-function',
            filters=[{'functionName': 'public-api'}],
            actions=[{'type': 'tag', 'key': 'c7n', 'value': 'tagged'}])
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = factory().client('lambda-web').list_tags(
            resource=resources[0]['functionArn'])['tags']
        self.assertEqual(tags['c7n'], 'tagged')

    def test_remove_tag(self):
        p, factory = self.load(
            'test_lambda_web_function_remove_tag', 'aws.lambda-web-function',
            filters=[{'functionName': 'public-api'}],
            actions=[{'type': 'remove-tag', 'tags': ['owner']}])
        resources = p.run()
        tags = factory().client('lambda-web').list_tags(
            resource=resources[0]['functionArn'])['tags']
        self.assertEqual(tags, {})

    def test_mark_for_op_and_marked_for_op_schema(self):
        p = self.load_policy({
            'name': 'lambda-web-mark',
            'resource': 'aws.lambda-web-function',
            'filters': [{'type': 'marked-for-op', 'op': 'delete'}],
            'actions': [{'type': 'mark-for-op', 'op': 'delete', 'days': 7}]})
        self.assertEqual(len(p.resource_manager.actions), 1)

    def test_delete(self):
        p, factory = self.load(
            'test_lambda_web_function_delete', 'aws.lambda-web-function',
            filters=[{'type': 'endpoint', 'key': 'authType', 'value': 'ApplicationManaged'}],
            actions=['delete'])
        captor = ApiCallCaptor.start_capture()
        resources = p.run()
        self.assertEqual([r['functionName'] for r in resources], ['public-api'])
        self.assertEqual(
            [c['params'] for c in captor.calls if c['operation'] == 'DeleteWebFunction'],
            [{'functionName': 'public-api'}])
        client = factory().client('lambda-web')
        with self.assertRaises(client.exceptions.ResourceNotFoundException):
            client.get_web_function(functionName='public-api')

    def get_remove_statements_action(self, statement_ids='matched'):
        p = self.load_policy({
            'name': 'lambda-web-remove-statements',
            'resource': 'aws.lambda-web-function',
            'actions': [{'type': 'remove-statements', 'statement_ids': statement_ids}]})
        return p.resource_manager.actions[0]

    @staticmethod
    def policy_client(statements):
        client = mock.MagicMock()
        client.exceptions.ResourceNotFoundException = ClientError
        client.get_resource_policy.return_value = {
            'policy': json.dumps({'Version': '2012-10-17', 'Statement': statements}),
            'revisionId': 'rev-1'}
        return client

    def test_remove_statements_puts_remaining_policy(self):
        keep = {'Sid': 'Keep', 'Effect': 'Allow', 'Principal': {'AWS': ACCOUNT}}
        drop = {'Sid': 'Drop', 'Effect': 'Allow', 'Principal': {'AWS': '999988887777'}}
        client = self.policy_client([keep, drop])
        action = self.get_remove_statements_action(['Drop'])
        resource = {'functionName': 'scoped-api', 'functionArn': FUNCTION_ARN}
        self.assertTrue(action.process_resource(client, resource))
        client.delete_resource_policy.assert_not_called()
        kw = client.put_resource_policy.call_args.kwargs
        self.assertEqual(kw['resourceArn'], FUNCTION_ARN)
        self.assertEqual(kw['revisionId'], 'rev-1')
        self.assertEqual(json.loads(kw['policy'])['Statement'], [keep])

    def test_remove_statements_deletes_empty_policy(self):
        client = self.policy_client([{'Sid': 'Drop', 'Effect': 'Allow'}])
        action = self.get_remove_statements_action('matched')
        resource = {
            'functionName': 'scoped-api', 'functionArn': FUNCTION_ARN,
            'CrossAccountViolations': [{'Sid': 'Drop', 'Effect': 'Allow'}]}
        self.assertTrue(action.process_resource(client, resource))
        client.put_resource_policy.assert_not_called()
        client.delete_resource_policy.assert_called_once_with(
            resourceArn=FUNCTION_ARN, revisionId='rev-1')

    def test_remove_statements_single_statement_object(self):
        drop = {'Sid': 'Drop', 'Effect': 'Allow', 'Principal': {'AWS': '999988887777'}}
        client = self.policy_client(drop)
        action = self.get_remove_statements_action(['Drop'])
        resource = {'functionName': 'scoped-api', 'functionArn': FUNCTION_ARN}
        self.assertTrue(action.process_resource(client, resource))
        client.delete_resource_policy.assert_called_once_with(
            resourceArn=FUNCTION_ARN, revisionId='rev-1')

    def test_remove_statements_without_revision_id(self):
        client = self.policy_client([{'Sid': 'Drop', 'Effect': 'Allow'}])
        client.get_resource_policy.return_value.pop('revisionId')
        action = self.get_remove_statements_action(['Drop'])
        resource = {'functionName': 'scoped-api', 'functionArn': FUNCTION_ARN}
        self.assertTrue(action.process_resource(client, resource))
        client.delete_resource_policy.assert_called_once_with(resourceArn=FUNCTION_ARN)

    def test_delete_function_conflict_continues(self):
        p = self.load_policy({
            'name': 'lambda-web-delete', 'resource': 'aws.lambda-web-function',
            'actions': ['delete']})
        client = mock.MagicMock()
        client.exceptions.ResourceNotFoundException = KeyError
        client.exceptions.ConflictException = ClientError
        client.delete_web_function.side_effect = [
            ClientError({'Error': {'Code': 'ConflictException'}}, 'x'), {}]
        with mock.patch('c7n.resources.awslambda.local_session') as session:
            session.return_value.client.return_value = client
            p.resource_manager.actions[0].process(
                [{'functionName': 'a'}, {'functionName': 'b'}])
        self.assertEqual(client.delete_web_function.call_count, 2)

    def test_remove_statements_failure_is_reported(self):
        action = self.get_remove_statements_action(['Drop'])
        client = self.policy_client([{'Sid': 'Drop', 'Effect': 'Allow'}])
        client.delete_resource_policy.side_effect = ClientError(
            {'Error': {'Code': 'ConflictException'}}, 'DeleteResourcePolicy')
        good = {'functionName': 'ok', 'functionArn': FUNCTION_ARN}
        bad = {'functionName': 'bad', 'functionArn': FUNCTION_ARN + '-bad'}
        client.get_resource_policy.side_effect = lambda resourceArn: (
            self.policy_client([{'Sid': 'Keep'}]).get_resource_policy.return_value
            if resourceArn == FUNCTION_ARN
            else self.policy_client([{'Sid': 'Drop'}]).get_resource_policy.return_value)
        with mock.patch('c7n.resources.awslambda.local_session') as session:
            session.return_value.client.return_value = client
            with self.assertRaises(PolicyExecutionError) as ctx:
                action.process([good, bad])
        self.assertIn('failed for 1 web function', str(ctx.exception))
        self.assertIn(FUNCTION_ARN + '-bad', str(ctx.exception))

    def test_remove_statements_no_match_or_no_policy(self):
        action = self.get_remove_statements_action(['Nope'])
        resource = {'functionName': 'scoped-api', 'functionArn': FUNCTION_ARN}
        client = self.policy_client([{'Sid': 'Keep', 'Effect': 'Allow'}])
        self.assertFalse(action.process_resource(client, resource))
        client.put_resource_policy.assert_not_called()

        client = mock.MagicMock()
        client.exceptions.ResourceNotFoundException = ClientError
        client.get_resource_policy.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}}, 'GetResourcePolicy')
        self.assertFalse(action.process_resource(client, resource))


class LambdaWebEndpointTest(LambdaWebTest):

    PUBLIC_FILTERS = [{
        'or': [
            {'type': 'value', 'key': 'authType', 'value': 'ApplicationManaged'},
            {'and': [
                {'type': 'value', 'key': 'authType', 'value': 'IamAuth'},
                {'type': 'cross-account',
                 'actions': ['lambda:InvokeWebFunctionEndpoint']}]}]}]

    def test_query(self):
        p, _ = self.load('test_lambda_web_endpoint_query', 'aws.lambda-web-endpoint')
        resources = p.run()
        self.assertEqual(
            [(r['c7n:parent-id'], r['endpointName']) for r in resources],
            [('public-api', 'prod'), ('public-api', 'internal'),
             ('partner-api', 'main'), ('scoped-api', 'a'), ('scoped-api', 'b')])
        self.assertEqual(
            p.resource_manager.get_arns(resources[:1]),
            ['arn:aws:lambda:us-east-1:%s:web-function/public-api/endpoint/prod' % ACCOUNT])

    def test_auth_type_filter(self):
        p, _ = self.load(
            'test_lambda_web_endpoint_query', 'aws.lambda-web-endpoint',
            filters=[{'authType': 'ApplicationManaged'}])
        resources = p.run()
        self.assertEqual([r['endpointName'] for r in resources], ['prod'])

    def test_public_policy(self):
        """The CLOP-45401 public exposure definition."""
        p, _ = self.load(
            'test_lambda_web_endpoint_public', 'aws.lambda-web-endpoint',
            filters=self.PUBLIC_FILTERS)
        resources = p.run()
        self.assertEqual(
            sorted((r['c7n:parent-id'], r['endpointName']) for r in resources),
            [('partner-api', 'main'),      # cross account role, IamAuth
             ('public-api', 'prod'),       # ApplicationManaged
             ('scoped-api', 'a')])         # cross account, scoped to this endpoint only

    def test_cross_account_scoped_to_endpoint(self):
        p, _ = self.load(
            'test_lambda_web_endpoint_public', 'aws.lambda-web-endpoint',
            filters=[{'type': 'cross-account'}])
        resources = p.run()
        names = sorted((r['c7n:parent-id'], r['endpointName']) for r in resources)
        self.assertEqual(names, [('partner-api', 'main'), ('scoped-api', 'a')])
        self.assertNotIn(('scoped-api', 'b'), names)

    def test_set_auth_type(self):
        p, factory = self.load(
            'test_lambda_web_endpoint_set_auth_type', 'aws.lambda-web-endpoint',
            filters=[{'authType': 'ApplicationManaged'}],
            actions=[{'type': 'set-auth-type', 'auth_type': 'IamAuth'}])
        resources = p.run()
        self.assertEqual(len(resources), 1)
        endpoint = factory().client('lambda-web').get_web_function_endpoint(
            functionName='public-api', endpointName='prod')
        self.assertEqual(endpoint['authType'], 'IamAuth')

    def test_delete(self):
        p, factory = self.load(
            'test_lambda_web_endpoint_delete', 'aws.lambda-web-endpoint',
            filters=[{'authType': 'ApplicationManaged'}], actions=['delete'])
        captor = ApiCallCaptor.start_capture()
        self.assertEqual(len(p.run()), 1)
        self.assertEqual(
            [c['params'] for c in captor.calls
             if c['operation'] == 'DeleteWebFunctionEndpoint'],
            [{'functionName': 'public-api', 'endpointName': 'prod'}])
        client = factory().client('lambda-web')
        with self.assertRaises(client.exceptions.ResourceNotFoundException):
            client.get_web_function_endpoint(
                functionName='public-api', endpointName='prod')

    def test_actions_call_expected_apis(self):
        client = mock.MagicMock()
        p = self.load_policy({
            'name': 'lambda-web-endpoint-actions',
            'resource': 'aws.lambda-web-endpoint',
            'actions': [{'type': 'set-auth-type'}]})
        endpoint = {'endpointName': 'prod', 'c7n:parent-id': 'public-api'}
        with mock.patch('c7n.resources.awslambda.local_session') as session:
            session.return_value.client.return_value = client
            p.resource_manager.actions[0].process([endpoint])
        client.update_web_function_endpoint.assert_called_once_with(
            functionName='public-api', endpointName='prod', authType='IamAuth')

    def test_get_resources(self):
        client = mock.MagicMock()
        client.exceptions.ResourceNotFoundException = ClientError
        client.get_web_function_endpoint.side_effect = [
            {'endpointArn': 'x', 'endpointName': 'prod', 'authType': 'IamAuth',
             'ResponseMetadata': {}},
            ClientError({'Error': {'Code': 'ResourceNotFoundException'}}, 'x')]
        p = self.load_policy({'name': 'e', 'resource': 'aws.lambda-web-endpoint'})
        base = 'arn:aws:lambda:us-east-1:%s:web-function/public-api/endpoint/' % ACCOUNT
        with mock.patch('c7n.resources.awslambda.local_session') as session:
            session.return_value.client.return_value = client
            found = p.resource_manager.get_resources([base + 'prod', base + 'gone'])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['c7n:parent-id'], 'public-api')
        client.get_web_function_endpoint.assert_any_call(
            functionName='public-api', endpointName='prod')


class ParseEndpointArnTest(BaseTest):

    def test_parse(self):
        self.assertEqual(
            parse_endpoint_arn(FUNCTION_ARN + '/endpoint/prod'),
            (FUNCTION_ARN, 'scoped-api', 'prod'))

    def test_invalid(self):
        for bad in ('scoped-api', FUNCTION_ARN, FUNCTION_ARN + '/endpoint/',
                    'arn:aws:lambda:us-east-1:%s:function:x/endpoint/y' % ACCOUNT):
            with self.assertRaises(ValueError):
                parse_endpoint_arn(bad)

    def test_get_resources_propagates_non_not_found_errors(self):
        p = self.load_policy({'name': 'e', 'resource': 'aws.lambda-web-endpoint'})
        client = mock.MagicMock()

        class NotFound(Exception):
            pass

        client.exceptions.ResourceNotFoundException = NotFound
        client.get_web_function_endpoint.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException'}}, 'GetWebFunctionEndpoint')
        with mock.patch('c7n.resources.awslambda.local_session') as session:
            session.return_value.client.return_value = client
            with self.assertRaises(ClientError):
                p.resource_manager.get_resources([FUNCTION_ARN + '/endpoint/prod'])

    def test_get_resources_skips_invalid_ids(self):
        p = self.load_policy({'name': 'e', 'resource': 'aws.lambda-web-endpoint'})
        client = mock.MagicMock()
        with mock.patch('c7n.resources.awslambda.local_session') as session:
            session.return_value.client.return_value = client
            self.assertEqual(p.resource_manager.get_resources(['bogus']), [])
        client.get_web_function_endpoint.assert_not_called()


class EndpointStatementScopeTest(BaseTest):

    ENDPOINT = FUNCTION_ARN + '/endpoint/a'

    def applies(self, statement):
        return _endpoint_statement_applies(statement, self.ENDPOINT, FUNCTION_ARN)

    def test_resource_scope(self):
        self.assertTrue(self.applies({'Resource': self.ENDPOINT}))
        self.assertTrue(self.applies({'Resource': [self.ENDPOINT]}))
        self.assertTrue(self.applies({'Resource': FUNCTION_ARN + '/endpoint/*'}))
        self.assertTrue(self.applies({'Resource': '*'}))
        self.assertTrue(self.applies({'Resource': FUNCTION_ARN}))
        self.assertFalse(self.applies({'Resource': FUNCTION_ARN + '/endpoint/b'}))
        self.assertFalse(self.applies({'Resource': [FUNCTION_ARN + '/endpoint/b']}))

    def test_not_resource_scope(self):
        self.assertFalse(self.applies({'NotResource': self.ENDPOINT}))
        self.assertTrue(self.applies({'NotResource': FUNCTION_ARN + '/endpoint/b'}))

    def test_not_resource_function_arn_does_not_exclude_endpoint(self):
        self.assertTrue(self.applies({'NotResource': FUNCTION_ARN}))
        self.assertFalse(self.applies({'NotResource': FUNCTION_ARN + '/endpoint/*'}))

    def test_no_resource_element(self):
        self.assertTrue(self.applies({'Sid': 'x'}))
