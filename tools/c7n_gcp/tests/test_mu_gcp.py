# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import copy
import functools
import json
import time
import os
import pathlib
import re
import shutil
import sys
import types

import pytest
from pytest_terraform import terraform

from c7n.exceptions import PolicyValidationError
from c7n.testing import functional

from c7n_gcp import client, handler, mu, policy

import gcp_common
import recorder
from gcp_common import BaseTest, event_data


HELLO_WORLD = """\
def handler(event, context):
    print("gcf handler invoke %s" % event)
"""


AUDIT_SELECTION_CASES = [
    ({}, (False, True)),
    ({'first': True}, (True, False)),
    ({'first': False}, (False, True)),
    ({'last': True}, (False, True)),
    ({'last': False}, (False, False)),
    ({'first': True, 'last': False}, (True, False)),
    ({'first': False, 'last': True}, (False, True)),
    ({'first': True, 'last': True}, (True, True)),
    ({'first': False, 'last': False}, (False, False)),
]


@pytest.mark.parametrize('options,expected', AUDIT_SELECTION_CASES)
def test_audit_record_selection_defaults(options: dict, expected: tuple) -> None:
    original = options.copy()
    assert mu.get_audit_record_selection(options) == expected
    assert options == original


@pytest.mark.parametrize('options,expected', AUDIT_SELECTION_CASES)
def test_audit_record_selection_validation(test, options: dict, expected: tuple) -> None:
    data = {
        'name': 'audit-selection',
        'resource': 'gcp.instance',
        'mode': {'type': 'gcp-audit', 'methods': ['method.a'], **options},
    }

    if any(expected):
        p = test.load_policy(data)
        assert p.data == data
    else:
        with pytest.raises(PolicyValidationError, match='audit-selection.*first.*last'):
            test.load_policy(data)


@pytest.mark.parametrize('field', ['first', 'last'])
@pytest.mark.parametrize('value', ['true', 0, 1, None])
def test_audit_record_selection_schema(test, field: str, value: object) -> None:
    with pytest.raises(PolicyValidationError):
        test.load_policy({
            'name': 'audit-selection',
            'resource': 'gcp.instance',
            'mode': {'type': 'gcp-audit', 'methods': ['method.a'], field: value},
        }, validate=True)


def test_audit_retrieval_validation_unchanged(test, monkeypatch) -> None:
    p = test.load_policy({
        'name': 'audit-selection',
        'resource': 'gcp.instance',
        'mode': {'type': 'gcp-audit', 'methods': ['method.a']},
    })
    monkeypatch.setattr(p.resource_manager.resource_type, 'get', None)

    with pytest.raises(PolicyValidationError, match='does not implement retrieval method'):
        p.get_execution_mode().validate()


@pytest.mark.parametrize('options,phase_filter', [
    ({}, 'operation.last = true'),
    ({'first': False}, 'operation.last = true'),
    ({'last': True}, 'operation.last = true'),
    ({'first': False, 'last': True}, 'operation.last = true'),
    ({'first': True}, 'operation.first = true'),
    ({'first': True, 'last': False}, 'operation.first = true'),
    ({'first': True, 'last': True}, 'operation.first = true OR operation.last = true'),
])
def test_audit_record_selection_filter(options: dict, phase_filter: str) -> None:
    data = {'methods': ['method.a', 'method.b'], **options}
    original = data.copy()
    session = types.SimpleNamespace(get_default_project=lambda: 'selection-project')
    func = types.SimpleNamespace(name='selection')
    subscription = mu.ApiSubscriber(session, data).get_subscription(func)
    assert subscription == {
        'topic': 'custodian-auto-audit-selection',
        'name': 'custodian-auto-audit-selection',
        'log': 'projects/selection-project/logs/cloudaudit.googleapis.com%2Factivity',
        'filter': (
            'logName = "projects/selection-project/logs/cloudaudit.googleapis.com%2Factivity"'
            ' AND protoPayload.methodName = ("method.a" OR "method.b")'
            ' AND ((NOT operation.first:* AND NOT operation.last:*)'
            f' OR {phase_filter})'
        ),
    }
    assert data == original


@pytest.fixture
def sanitized_audit_flights(test, monkeypatch) -> None:
    sanitize_project = recorder.sanitize_project_name

    def sanitize(value: str) -> str:
        value = sanitize_project(value).replace(test.project_id, recorder.PROJECT_ID)

        if '"entries":' in value:
            value = gcp_common.EMAIL_RE.sub(gcp_common.PLACEHOLDER_EMAIL, value)
            value = re.sub(
                r'("callerIp":\s*)"[^"]*"',
                rf'\1"{gcp_common.PLACEHOLDER_IP}"',
                value,
            )

        return value

    monkeypatch.setattr(recorder, 'sanitize_project_name', sanitize)


def test_audit_record_selection_sanitization(test, sanitized_audit_flights) -> None:
    # Sanitization must not collapse the distinct IAM identities used in sink setup.
    source = json.dumps({
        'entries': [{'principalEmail': 'developer@company.example', 'callerIp': '1.2.3.4'}],
        'project_id': test.project_id,
    })
    result = json.loads(recorder.sanitize_project_name(source))
    assert result['project_id'] == recorder.PROJECT_ID
    assert result['entries'] == [{
        'principalEmail': 'user@example.com',
        'callerIp': '198.51.100.1',
    }]
    iam = json.dumps({'members': ['serviceAccount:logging@system.gserviceaccount.com']})
    assert recorder.sanitize_project_name(iam) == iam


@terraform('gcp_audit_record_selection', scope='session')
def test_audit_record_selection_sink(
        test, gcp_audit_record_selection, monkeypatch, sanitized_audit_flights,
) -> None:
    state = gcp_audit_record_selection
    topic = state['google_pubsub_topic.audit.name']
    func = types.SimpleNamespace(name=state['google_compute_instance.default.name'])
    factory = test.replay_flight_data('audit-record-selection-sink')
    session = factory()
    sink_client = session.client('logging', 'v2', 'projects.sinks')
    commands = []
    execute = type(sink_client).execute_command

    def capture(service, method: str, arguments: dict):
        commands.append((method, copy.deepcopy(arguments)))
        return execute(service, method, arguments)

    monkeypatch.setattr(type(sink_client), 'execute_command', capture)
    methods = ['v1.compute.instances.insert']
    subscriber = mu.ApiSubscriber(session, {'methods': methods})
    test.addCleanup(subscriber.remove, func)

    for selection in ({}, {'first': True}, {'first': True, 'last': True}):
        subscriber = mu.ApiSubscriber(session, {'methods': methods, **selection})
        subscription = subscriber.get_subscription(func)
        subscriber.add(func)
        sink = sink_client.execute_command('get', {
            'sinkName': f'projects/{test.project_id}/sinks/{subscription["name"]}',
        })
        assert sink['filter'] == subscription['filter']
        assert sink['destination'] == (
            f'pubsub.googleapis.com/projects/{test.project_id}/topics/{topic}'
        )

    assert len([args for method, args in commands if method == 'create']) == 1
    updates = [args for method, args in commands if method == 'update']
    assert len(updates) == 2
    assert all(args['updateMask'] == 'filter' for args in updates)
    subscriber.add(func)
    assert len([args for method, args in commands if method == 'update']) == 2


@terraform('gcp_audit_record_selection', scope='session')
def test_audit_record_selection_entries(
        test, gcp_audit_record_selection, sanitized_audit_flights,
) -> None:
    name = gcp_audit_record_selection['google_compute_instance.default.id']
    method = 'v1.compute.instances.insert'
    factory = test.replay_flight_data('audit-record-selection-entries')

    if test.recording:
        # Replace this test's event pair so queries use the newly created operation.
        for phase in ('first', 'last'):
            pathlib.Path(
                gcp_common.EVENT_DIR,
                f'audit-record-selection-create-{phase}.json',
            ).unlink(missing_ok=True)

        setup_factory = functools.partial(client.Session, project_id=test.project_id)
        gcp_common.audit_event_recorder(
            setup_factory,
            'audit-record-selection-create.json',
            method=method,
            resource_name=name,
            start_time_skew_seconds=900,
        ).record()
        test.cleanUp()

    first = event_data('audit-record-selection-create-first.json')
    last = event_data('audit-record-selection-create-last.json')
    assert first['operation']['id'] == last['operation']['id']
    assert first['operation']['first'] and last['operation']['last']
    assert first['insertId'] != last['insertId']
    session = factory()
    entries_client = session.client('logging', 'v2', 'entries')
    func = types.SimpleNamespace(name='selection')

    # Query the exact sink expressions: Google, not a Python evaluator, selects records.
    for selection, expected in (
        ({}, {last['insertId']}),
        ({'first': True}, {first['insertId']}),
        ({'first': False, 'last': True}, {last['insertId']}),
        ({'first': True, 'last': True}, {first['insertId'], last['insertId']}),
    ):
        subscription = mu.ApiSubscriber(
            session,
            {'methods': [method], **selection},
        ).get_subscription(func)
        query_filter = (
            f'{subscription["filter"]}'
            f' AND protoPayload.resourceName = {json.dumps(name)}'
            f' AND operation.id = {json.dumps(first["operation"]["id"])}'
            f' AND timestamp >= {json.dumps(first["timestamp"])}'
        )
        entries = []

        for page in entries_client.execute_paged_query('list', {'body': {
            'resourceNames': [f'projects/{test.project_id}'],
            'filter': query_filter,
            'orderBy': 'timestamp asc',
        }}):
            entries.extend(page.get('entries', []))

        assert {e['insertId'] for e in entries} == expected
        assert len(entries) == len(expected)


class FunctionTest(BaseTest):

    def get_function(self, events=(), factory=None, **kw):
        if not events:
            assert factory
            events = [mu.HTTPEvent(factory)]
        config = dict(
            name="custodian-dev",
            labels=[],
            runtime='python37',
            events=events)
        config.update(kw)
        archive = mu.custodian_archive()
        archive.close()
        return mu.CloudFunction(config, archive)

    def test_archive_files(self):
        archive = mu.custodian_archive()
        archive.close()
        assert "c7n_gcp/filters/recommender.json" in archive.get_filenames()

    def test_deploy_function(self):
        factory = self.replay_flight_data('mu-deploy')
        manager = mu.CloudFunctionManager(factory, 'us-central1')
        func = self.get_function(factory=factory)
        manager.publish(func)
        func_info = manager.get(func.name)
        self.assertTrue(func_info['httpsTrigger'])
        self.assertEqual(func_info['status'], 'DEPLOY_IN_PROGRESS')
        self.assertEqual(
            func_info['name'],
            'projects/cloud-custodian/locations/us-central1/functions/custodian-dev')

    def test_handler_run(self):
        func_cwd = self.get_temp_dir()
        output_temp = self.get_temp_dir()
        pdata = {
            'name': 'dataset-created',
            'resource': 'gcp.bq-dataset',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['datasetservice.insert']}}

        with open(os.path.join(func_cwd, 'config.json'), 'w') as fh:
            fh.write(json.dumps({'policies': [pdata]}))

        event = event_data('bq-dataset-create.json')
        p = self.load_policy(pdata)

        from c7n.policy import PolicyCollection
        self.patch(PolicyCollection, 'from_data', staticmethod(lambda *args, **kw: [p]))
        self.patch(p, 'push', lambda evt, ctx: None)
        self.patch(handler, 'get_tmp_output_dir', lambda: output_temp)

        self.change_cwd(func_cwd)
        self.assertEqual(handler.run(event), True)

    def test_handler_tmp_dir(self):
        # platform specific test ..
        if sys.platform not in ('linux2', 'darwin'):
            return
        tmp_dir = handler.get_tmp_output_dir()
        self.assertTrue(tmp_dir.startswith('/tmp'))
        self.addCleanup(shutil.rmtree, tmp_dir)

    def test_abstract_gcp_mode(self):
        # this will fetch a discovery
        factory = self.replay_flight_data('mu-gcp-abstract')
        p = self.load_policy({
            'name': 'instance', 'resource': 'gcp.instance'},
            session_factory=factory)
        exec_mode = policy.FunctionMode(p)
        self.assertRaises(NotImplementedError, exec_mode.run, {}, None)
        self.assertRaises(NotImplementedError, exec_mode.provision)
        self.assertEqual(None, exec_mode.validate())

    def test_policy_context_deps(self):
        p = self.load_policy({
            'name': 'check',
            'resource': 'gcp.instance',
            'mode': {
                'type': 'gcp-periodic',
                'service-account': 'foo',
                'schedule': 'every 2 hours'}},
            output_dir='gs://somebucket/some-prefix',
            log_group='gcp',
            config={'metrics': 'gcp'})
        pf = mu.PolicyFunction(p, archive=True)
        self.assertEqual(
            pf.get_output_deps(),
            ['google-cloud-monitoring',
             'google-cloud-storage',
             'google-cloud-logging'])

    def test_periodic_validate_tz(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {'name': 'instance-off',
             'resource': 'gcp.instance',
             'mode': {'type': 'gcp-periodic',
                      'service-account': 'foo',
                      'schedule': 'every 2 hours',
                      'tz': 'zulugold'}})

    def test_periodic_validate_service_account(self):
        # no target type or http should require service-account
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {'name': 'instance-off',
             'resource': 'gcp.instance',
             'mode': {'type': 'gcp-periodic',
                      'schedule': 'every 2 hours'}})

        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {'name': 'instance-off',
             'resource': 'gcp.instance',
             'mode': {'type': 'gcp-periodic',
                      'target-type': 'http',
                      'schedule': 'every 2 hours'}})

        # pubsub target type should not require service-account
        self.load_policy(
            {
                'name': 'instance-off',
                'resource': 'gcp.instance',
                'mode': {
                    'type': 'gcp-periodic',
                    'target-type': 'pubsub',
                    'schedule': 'every 2 hours'
                }
            }
        )

    def test_periodic_update_schedule(self):
        factory = self.replay_flight_data('mu-perodic-update-schedule')
        session = factory()
        project_id = self.project_id
        region = 'us-central1'

        sched_client = session.client('cloudscheduler', 'v1beta1', 'projects.locations.jobs')
        job_v1 = sched_client.execute_query(
            'get',
            {'name': 'projects/{}/locations/{}/jobs/{}'.format(
                project_id, region, 'custodian-auto-gcp-find-instances')})

        p = self.load_policy({
            'name': 'gcp-find-instances',
            'resource': 'gcp.instance',
            'mode': {
                'type': 'gcp-periodic',
                'schedule': 'every 2 hours',
                'service-account': 'foo'}},
            session_factory=factory)
        p.run()

        job_v2 = sched_client.execute_query(
            'get',
            {'name': 'projects/{}/locations/{}/jobs/{}'.format(
                project_id, region, 'custodian-auto-gcp-find-instances')})
        self.assertEqual(job_v1['schedule'], 'every 3 hours')
        self.assertEqual(job_v2['schedule'], 'every 2 hours')

    @functional
    def test_periodic_subscriber(self):
        factory = self.replay_flight_data('mu-perodic')
        p = self.load_policy({
            'name': 'instance-off',
            'resource': 'gcp.instance',
            'mode': {
                'type': 'gcp-periodic',
                'environment': {'Env': 'Dev'},
                'schedule': 'every 2 hours',
                'service-account': 'foo'}},
            session_factory=factory)

        p.provision()

        session = factory()
        project_id = self.project_id
        region = 'us-central1'

        func_client = session.client('cloudfunctions', 'v1', 'projects.locations.functions')

        # check function exists
        func_info = func_client.execute_command(
            'get', {'name': 'projects/{}/locations/{}/functions/instance-off'.format(
                project_id, region)})
        self.assertEqual(
            "https://{}-{}.cloudfunctions.net/{}".format(
                region, project_id, 'instance-off'),
            func_info['httpsTrigger']['url'])

        sched_client = session.client('cloudscheduler', 'v1beta1', 'projects.locations.jobs')
        job = sched_client.execute_query(
            'get',
            {'name': 'projects/{}/locations/{}/jobs/{}'.format(
                project_id, region, 'custodian-auto-instance-off')})
        self.assertEqual(job['schedule'], 'every 2 hours')
        self.assertEqual(job['timeZone'], 'Etc/UTC')

        if self.recording:
            time.sleep(52)
        p.get_execution_mode().deprovision()

    def test_api_subscriber_run(self):
        factory = self.replay_flight_data('mu-api-subscriber-run')
        p = self.load_policy({
            'name': 'dataset-created',
            'resource': 'gcp.bq-dataset',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['datasetservice.insert']}},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        self.assertTrue(isinstance(exec_mode, policy.ApiAuditMode))
        event = event_data('bq-dataset-create.json')
        resources = exec_mode.run(event, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['labels'], {'env': 'dev'})

    @functional
    def test_api_subscriber(self):
        # integration styled..

        factory = self.replay_flight_data('mu-api-subscriber')
        p = self.load_policy(
            {'name': 'topic-created',
             'resource': 'gcp.pubsub-topic',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['google.pubsub.v1.Publisher.CreateTopic']}},
            session_factory=factory)

        # Create all policy resources.
        p.provision()

        session = factory()
        project_id = self.project_id
        region = 'us-central1'
        func_client = session.client('cloudfunctions', 'v1', 'projects.locations.functions')
        pubsub_client = session.client('pubsub', 'v1', 'projects.topics')
        sink_client = session.client('logging', 'v2', 'projects.sinks')

        # Check on the resources for the api subscription

        # check function exists
        func_info = func_client.execute_command(
            'get', {'name': 'projects/{}/locations/{}/functions/topic-created'.format(
                project_id, region)})
        self.assertEqual(
            func_info['eventTrigger']['eventType'],
            'providers/cloud.pubsub/eventTypes/topic.publish')
        self.assertEqual(
            func_info['eventTrigger']['resource'],
            'projects/{}/topics/custodian-auto-audit-topic-created'.format(
                project_id))

        # check sink exists
        sink = sink_client.execute_command(
            'get', {'sinkName': 'projects/{}/sinks/custodian-auto-audit-topic-created'.format(
                project_id)})
        self.assertEqual(
            sink['destination'],
            'pubsub.googleapis.com/projects/{}/topics/custodian-auto-audit-topic-created'.format(
                project_id))

        # check the topic iam policy
        topic_policy = pubsub_client.execute_command(
            'getIamPolicy', {
                'resource': 'projects/{}/topics/custodian-auto-audit-topic-created'.format(
                    project_id)})
        self.assertEqual(
            topic_policy['bindings'],
            [{u'role': u'roles/pubsub.publisher', u'members': [sink['writerIdentity']]}])

        # todo set this up as test cleanups, dependent on ordering at the moment, fifo atm
        # it appears, we want lifo.
        if self.recording:
            # we sleep to allow time for in progress operations on creation to complete
            # function requirements building primarily.
            time.sleep(42)
        p.get_execution_mode().deprovision()

    @functional
    def test_scc_subscriber(self):

        project_id = self.project_id
        org = 111111111111
        factory = self.replay_flight_data('mu-scc-subscriber', project_id=project_id)
        p = self.load_policy(
            {'name': 'test-scc',
             'resource': 'gcp.bucket',
             'mode': {
                 'type': 'gcp-scc',
                 'org': org}},
            session_factory=factory)

        # Create all policy resources.
        p.provision()

        session = factory()
        region = 'us-central1'
        func_client = session.client('cloudfunctions', 'v1', 'projects.locations.functions')
        pubsub_client = session.client('pubsub', 'v1', 'projects.topics')
        notification_client = session.client('securitycenter', 'v1',
            'organizations.notificationConfigs')

        # Check on the resources for the scc subscription

        pubsub_topic = 'projects/{}/topics/custodian-auto-scc-bucket'.format(
            project_id)
        # check function exists
        func_info = func_client.execute_command(
            'get', {'name': 'projects/{}/locations/{}/functions/test-scc'.format(
                project_id, region)})
        self.assertEqual(
            func_info['eventTrigger']['eventType'],
            'providers/cloud.pubsub/eventTypes/topic.publish')
        self.assertEqual(
            func_info['eventTrigger']['resource'],
            pubsub_topic)

        # check notification config exists
        config_name = "organizations/{}/notificationConfigs/{}".format(org,
         "custodian-auto-scc-bucket")

        notification_config = notification_client.execute_command(
            'get', {'name': config_name})
        self.assertEqual(
            notification_config['pubsubTopic'], pubsub_topic)

        # check topic exists
        topic_info = pubsub_client.execute_command(
            'get', {'topic': pubsub_topic})
        self.assertEqual(
            topic_info['name'], pubsub_topic)

        if self.recording:
            # we sleep to allow time for in progress operations on creation to complete
            # function requirements building primarily.
            time.sleep(42)
        p.get_execution_mode().deprovision()

    def test_scc_subscriber_run(self):
        project_id = self.project_id
        factory = self.replay_flight_data('mu-scc-subscriber-run', project_id=project_id)
        p = self.load_policy({
            'name': 'test-scc-run',
            'resource': 'gcp.subnet',
            'mode': {
                'type': 'gcp-scc',
                'org': 111111111111}},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        self.assertTrue(isinstance(exec_mode, policy.SecurityCenterMode))
        event = event_data('network-finding.json')
        resources = exec_mode.run(event, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], "a22222222222222222")
