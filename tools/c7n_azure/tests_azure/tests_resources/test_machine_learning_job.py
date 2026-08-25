# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import local_session
from c7n_azure.resources.machine_learning_job import MachineLearningJob
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser
from ..azure_common import BaseTest, arm_template, cassette_name


class MachineLearningJobTest(BaseTest):

    def test_machine_learning_job_schema_validate(self):
        p = self.load_policy({
            'name': 'find-all-machine-learning-jobs',
            'resource': 'azure.machine-learning-job'
        }, validate=True)
        self.assertTrue(p)

        p = self.load_policy({
            'name': 'cancel-machine-learning-jobs',
            'resource': 'azure.machine-learning-job',
            'actions': [{'type': 'cancel'}],
        }, validate=True)
        self.assertTrue(p)

        for action in ('tag', 'untag', 'auto-tag-user', 'auto-tag-date',
                       'tag-trim', 'mark-for-op'):
            self.assertNotIn(action, MachineLearningJob.action_registry)
        self.assertNotIn('marked-for-op', MachineLearningJob.filter_registry)
        self.assertNotIn('location', MachineLearningJob.resource_type.default_report_fields)

    @arm_template('machine-learning-job.json')
    @cassette_name('machine-learning-jobs')
    def test_machine_learning_job_query(self):
        p = self.load_policy({
            'name': 'find-all-machine-learning-jobs',
            'resource': 'azure.machine-learning-job',
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('cctest-sweep-job', resources[0]['name'])
        self.assertIn('/jobs/', resources[0]['id'])

    @arm_template('machine-learning-job.json')
    @cassette_name('machine-learning-jobs')
    def test_machine_learning_job_filter_sweep_parallelism(self):
        p = self.load_policy({
            'name': 'ml-sweep-jobs-over-parallelism-limit',
            'resource': 'azure.machine-learning-job',
            'filters': [{
                'type': 'value',
                'key': 'properties.jobType',
                'value': 'Sweep'
            }, {
                'type': 'value',
                'key': 'properties.limits.maxConcurrentTrials',
                'op': 'gt',
                'value': 10
            }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('cctest-sweep-job', resources[0]['name'])

    @arm_template('machine-learning-job-cancel.json')
    @cassette_name('machine-learning-job-cancel')
    def test_machine_learning_job_cancel(self):
        p = self.load_policy({
            'name': 'cancel-machine-learning-job',
            'resource': 'azure.machine-learning-job',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'op': 'in',
                'value': ['cctest-running-job', 'cctest-completed-job'],
            }],
            'actions': [{'type': 'cancel'}],
        }, validate=True, session_factory=Session)

        resources = p.run()
        self.assertEqual(
            {'cctest-running-job': 'Running', 'cctest-completed-job': 'Completed'},
            {r['name']: r['properties']['status'] for r in resources})

        running = [r for r in resources if r['name'] == 'cctest-running-job'][0]
        client = local_session(Session).client(
            'azure.mgmt.machinelearningservices.MachineLearningServicesMgmtClient')
        job = client.jobs.get(
            ResourceIdParser.get_resource_group(running['id']),
            ResourceIdParser.get_resource_name(running['c7n:parent-id']),
            running['name'],
        )
        self.assertEqual('CancelRequested', job.properties.status)

        # The completed job must not be cancelled: playback holds no cancel
        # interaction for it, so such a request would fail to match. Conversely
        # all_played requires that the running job's cancel POST was issued.
        self.assertTrue(self.cassette.all_played)
