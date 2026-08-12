# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

from c7n.utils import local_session
from c7n_azure.resources.machine_learning_job import (
    MachineLearningJob,
    MachineLearningJobArchiveAction,
)
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
            'name': 'archive-machine-learning-jobs',
            'resource': 'azure.machine-learning-job',
            'actions': [{'type': 'archive'}],
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

    def test_machine_learning_job_archive_action_updates_job(self):
        client = MagicMock()
        manager = MagicMock()
        manager.get_client.return_value = client
        resource = {
            'id': '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47'
                  '/resourceGroups/test_machine-learning-job/providers'
                  '/Microsoft.MachineLearningServices/workspaces/cctest-mlws'
                  '/jobs/cctest-sweep-job',
            'name': 'cctest-sweep-job',
            'c7n:parent-id': '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47'
                             '/resourceGroups/test_machine-learning-job/providers'
                             '/Microsoft.MachineLearningServices/workspaces/cctest-mlws',
            'properties': {'isArchived': False},
        }

        action = MachineLearningJobArchiveAction({'type': 'archive'}, manager)
        action._prepare_processing()
        action._process_resource(resource)

        self.assertTrue(resource['properties']['isArchived'])
        client.jobs.create_or_update.assert_called_once_with(
            resource_group_name='test_machine-learning-job',
            workspace_name='cctest-mlws',
            id='cctest-sweep-job',
            body=resource,
        )

    def test_machine_learning_job_archive_action_skips_archived_job(self):
        client = MagicMock()
        manager = MagicMock()
        manager.get_client.return_value = client
        resource = {
            'name': 'cctest-sweep-job',
            'properties': {'isArchived': True},
        }

        action = MachineLearningJobArchiveAction({'type': 'archive'}, manager)
        action._prepare_processing()
        action._process_resource(resource)

        client.jobs.create_or_update.assert_not_called()

    @cassette_name('machine-learning-job-archive')
    def test_machine_learning_job_archive(self):
        p = self.load_policy({
            'name': 'archive-machine-learning-job',
            'resource': 'azure.machine-learning-job',
            'filters': [{
                'type': 'value',
                'key': 'resourceGroup',
                'value': 'test_machine-learning-job-10949',
            }, {
                'type': 'value',
                'key': 'name',
                'value': 'happy_soursop_yptvy6nktn',
            }, {
                'type': 'value',
                'key': 'properties.status',
                'value': 'Completed',
            }, {
                'type': 'value',
                'key': 'properties.isArchived',
                'op': 'ne',
                'value': True,
            }],
            'actions': [{'type': 'archive'}],
        }, validate=True, session_factory=Session)

        resources = p.run()
        self.assertEqual(1, len(resources))

        client = local_session(Session).client(
            'azure.mgmt.machinelearningservices.MachineLearningServicesMgmtClient')
        job = client.jobs.get(
            ResourceIdParser.get_resource_group(resources[0]['id']),
            ResourceIdParser.get_resource_name(resources[0]['c7n:parent-id']),
            resources[0]['name'],
        )
        self.assertTrue(job.properties.is_archived)
