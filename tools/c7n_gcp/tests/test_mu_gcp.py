# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import time
import os
import shutil
import sys


from c7n.exceptions import PolicyValidationError
from c7n.testing import functional

from c7n_gcp import handler, mu, policy

from gcp_common import BaseTest, event_data


HELLO_WORLD = """\
def handler(event, context):
    print("gcf handler invoke %s" % event)
"""


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
        self.assertRaises(NotImplementedError, exec_mode.run)
        self.assertRaises(NotImplementedError, exec_mode.provision)
        self.assertEqual(None, exec_mode.validate())

    def test_policy_context_deps(self):
        p = self.load_policy({
            'name': 'check',
            'resource': 'gcp.instance',
            'mode': {
                'type': 'gcp-periodic',
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
                      'schedule': 'every 2 hours',
                      'tz': 'zulugold'}})

    def test_periodic_update_schedule(self):
        factory = self.replay_flight_data('mu-perodic-update-schedule')
        session = factory()
        project_id = 'cloud-custodian'
        region = 'us-central1'

        sched_client = session.client('cloudscheduler', 'v1beta1', 'projects.locations.jobs')
        job_v1 = sched_client.execute_query(
            'get',
            {'name': 'projects/{}/locations/{}/jobs/{}'.format(
                project_id, region, 'custodian-auto-gcp-find-instances')})

        p = self.load_policy({
            'name': 'gcp-find-instances',
            'resource': 'gcp.instance',
            'mode': {'type': 'gcp-periodic', 'schedule': 'every 2 hours'}},
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
            'mode': {'type': 'gcp-periodic', 'schedule': 'every 2 hours'}},
            session_factory=factory)

        p.provision()

        session = factory()
        project_id = 'cloud-custodian'
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
        project_id = 'cloud-custodian'
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
