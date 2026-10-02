# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
from unittest import mock

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
import pytest

from c7n.exceptions import PolicyExecutionError, PolicyValidationError


ANALYZER_NAME = 'custodian-external-access'
ANALYZER_ARN = 'arn:aws:access-analyzer:us-east-1:123456789012:analyzer/' + ANALYZER_NAME


@pytest.fixture
def analyzer_session():
    session = boto3.Session(
        region_name='us-east-1', aws_access_key_id='test', aws_secret_access_key='test')
    clients = {name: session.client(name) for name in ('accessanalyzer', 'iam')}
    stub_session = mock.Mock(client=lambda name: clients[name])

    def factory():
        return stub_session
    with Stubber(clients['accessanalyzer']) as analyzer, Stubber(clients['iam']) as iam:
        yield factory, analyzer, iam
        analyzer.assert_no_pending_responses()
        iam.assert_no_pending_responses()


def analyzer_summary(analyzer_type='ACCOUNT'):
    return {
        'arn': ANALYZER_ARN,
        'name': ANALYZER_NAME,
        'type': analyzer_type,
        'status': 'ACTIVE',
        'createdAt': datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    }


def load_analyzer_policy(test, factory=None, **options):
    return test.load_policy({
        'name': 'create-access-analyzer',
        'resource': 'aws.account',
        'actions': [{
            'type': 'create-access-analyzer',
            'analyzer-name': ANALYZER_NAME,
            **options,
        }],
    }, session_factory=factory)


def test_create_access_analyzer_repeated_run(test, analyzer_session):
    factory, analyzer, _ = analyzer_session
    analyzer.add_client_error(
        'get_analyzer', service_error_code='ResourceNotFoundException',
        http_status_code=404, expected_params={'analyzerName': ANALYZER_NAME})
    analyzer.add_response('create_analyzer', {'arn': ANALYZER_ARN}, {
        'analyzerName': ANALYZER_NAME, 'type': 'ACCOUNT'})
    analyzer.add_response('get_analyzer', {'analyzer': analyzer_summary()}, {
        'analyzerName': ANALYZER_NAME})
    policy = load_analyzer_policy(test, factory)
    action = policy.resource_manager.actions[0]
    original = dict(action.data)

    action.process([{'account_id': '123456789012'}])
    action.process([{'account_id': '123456789012'}])

    assert action.data == original


def test_create_access_analyzer_options(test, analyzer_session):
    factory, analyzer, _ = analyzer_session
    rules = [{'ruleName': 'trusted-account', 'filter': {
        'principal.AWS': {'eq': ['123456789012']}}}]
    tags = {'Owner': 'Security'}
    analyzer.add_client_error(
        'get_analyzer', service_error_code='ResourceNotFoundException',
        http_status_code=404, expected_params={'analyzerName': ANALYZER_NAME})
    analyzer.add_response('create_analyzer', {'arn': ANALYZER_ARN}, {
        'analyzerName': ANALYZER_NAME, 'type': 'ORGANIZATION',
        'archiveRules': rules, 'tags': tags})
    policy = load_analyzer_policy(test, factory, **{
        'analyzer-type': 'ORGANIZATION', 'archive-rules': rules, 'tags': tags})

    policy.resource_manager.actions[0].process([{'account_id': '123456789012'}])


def test_create_access_analyzer_type_conflict(test, analyzer_session):
    factory, analyzer, _ = analyzer_session
    analyzer.add_response('get_analyzer', {'analyzer': analyzer_summary('ORGANIZATION')}, {
        'analyzerName': ANALYZER_NAME})
    policy = load_analyzer_policy(test, factory)

    with pytest.raises(PolicyExecutionError, match='ORGANIZATION.*ACCOUNT'):
        policy.resource_manager.actions[0].process([{'account_id': '123456789012'}])


@pytest.mark.parametrize('operation,code', [
    ('get_analyzer', 'AccessDeniedException'),
    ('create_analyzer', 'AccessDeniedException'),
    ('create_analyzer', 'ServiceQuotaExceededException'),
    ('create_analyzer', 'ConflictException'),
])
def test_create_access_analyzer_api_error(test, analyzer_session, operation, code):
    factory, analyzer, _ = analyzer_session
    expected = {'analyzerName': ANALYZER_NAME}
    if operation == 'create_analyzer':
        analyzer.add_client_error(
            'get_analyzer', service_error_code='ResourceNotFoundException',
            http_status_code=404, expected_params=expected)
        expected = {**expected, 'type': 'ACCOUNT'}
    analyzer.add_client_error(operation, service_error_code=code, expected_params=expected)
    policy = load_analyzer_policy(test, factory)

    with pytest.raises(ClientError) as error:
        policy.resource_manager.actions[0].process([{'account_id': '123456789012'}])
    assert error.value.response['Error']['Code'] == code


@pytest.mark.parametrize('options', [
    {'analyzer-name': ''},
    {'analyzer-name': 'invalid/name'},
    {'analyzer-name': 'a' * 256},
    {'analyzer-type': 'ACCOUNT_UNUSED_ACCESS'},
    {'tags': {'Owner': 123}},
    {'archive-rules': [{'ruleName': 'missing-filter'}]},
    {'archive-rules': [{'ruleName': 'invalid', 'filter': {'isPublic': {'exists': 'yes'}}}]},
    {'archive-rules': [{'ruleName': 'invalid', 'filter': {}, 'unknown': True}]},
])
def test_create_access_analyzer_invalid_options(test, options):
    with pytest.raises(PolicyValidationError):
        load_analyzer_policy(test, **options)


def test_create_access_analyzer_requires_name(test):
    with pytest.raises(PolicyValidationError):
        test.load_policy({
            'name': 'missing-analyzer-name', 'resource': 'aws.account',
            'actions': [{'type': 'create-access-analyzer'}],
        })


@pytest.mark.parametrize('tags', [None, {'Owner': 'Security'}])
def test_create_access_analyzer_permissions(test, tags):
    policy = load_analyzer_policy(test, **({'tags': tags} if tags else {}))
    permissions = policy.resource_manager.actions[0].get_permissions()
    assert set(permissions) == {
        'access-analyzer:GetAnalyzer', 'access-analyzer:CreateAnalyzer',
        'iam:CreateServiceLinkedRole',
    } | ({'access-analyzer:TagResource'} if tags else set())


@pytest.mark.parametrize('existing_type', [None, 'ACCOUNT_UNUSED_ACCESS'])
def test_create_access_analyzer_with_account_filter(test, analyzer_session, existing_type):
    factory, analyzer, iam = analyzer_session
    for _ in range(2):
        iam.add_response('list_account_aliases', {'AccountAliases': []}, {})
    existing = [{
        **analyzer_summary(existing_type),
        'name': 'other-unused-access',
        'arn': 'arn:aws:access-analyzer:us-east-1:123456789012:analyzer/other-unused-access',
    }] if existing_type else []
    analyzer.add_response('list_analyzers', {'analyzers': existing}, {})
    analyzer.add_client_error(
        'get_analyzer', service_error_code='ResourceNotFoundException',
        http_status_code=404, expected_params={'analyzerName': ANALYZER_NAME})
    analyzer.add_response('create_analyzer', {'arn': ANALYZER_ARN}, {
        'analyzerName': ANALYZER_NAME, 'type': 'ACCOUNT'})
    analyzer.add_response('list_analyzers', {'analyzers': [analyzer_summary()]}, {})
    policy = test.load_policy({
        'name': 'enable-missing-access-analyzer',
        'resource': 'aws.account',
        'filters': [{'not': [{
            'type': 'access-analyzer', 'key': '[type, status]',
            'value': ['ACCOUNT', 'ACTIVE'],
        }]}],
        'actions': [{
            'type': 'create-access-analyzer', 'analyzer-name': ANALYZER_NAME,
        }],
    }, session_factory=factory)

    assert len(policy.run()) == 1
    assert policy.run() == []


@pytest.mark.parametrize('operation', ['get_analyzer', 'create_analyzer'])
def test_create_access_analyzer_retries_throttling(
        test, analyzer_session, monkeypatch, operation):
    factory, analyzer, _ = analyzer_session
    monkeypatch.setattr('c7n.utils.time.sleep', lambda _: None)
    expected = {'analyzerName': ANALYZER_NAME}
    if operation == 'create_analyzer':
        analyzer.add_client_error(
            'get_analyzer', service_error_code='ResourceNotFoundException',
            http_status_code=404, expected_params=expected)
        expected = {**expected, 'type': 'ACCOUNT'}
    analyzer.add_client_error(
        operation, service_error_code='ThrottlingException',
        http_status_code=429, expected_params=expected)
    response = {'analyzer': analyzer_summary()} if operation == 'get_analyzer' else {
        'arn': ANALYZER_ARN}
    analyzer.add_response(operation, response, expected)
    policy = load_analyzer_policy(test, factory)

    policy.resource_manager.actions[0].process([{'account_id': '123456789012'}])
