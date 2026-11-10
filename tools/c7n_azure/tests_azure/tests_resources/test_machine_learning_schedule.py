# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.mgmt.machinelearningservices.models import (
    CommandJob,
    JobScheduleAction,
    RecurrenceTrigger,
    Schedule,
    ScheduleProperties,
)
from c7n_azure.resources.machine_learning_schedule import MachineLearningSchedule

from ..azure_common import BaseTest, arm_template, cassette_name

RESOURCE_GROUP = 'test_machine-learning-schedule'

WORKSPACE_ID = (
    '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/VV'
    '/providers/Microsoft.MachineLearningServices/workspaces/{}'
)


class MachineLearningScheduleTest(BaseTest):

    recording_resource_group = RESOURCE_GROUP

    def test_machine_learning_schedule_query_args(self):
        parent = {
            'name': 'workspace',
            'resourceGroup': 'resource-group',
        }

        assert MachineLearningSchedule.resource_type.extra_args(parent) == {
            'resource_group_name': 'resource-group',
            'workspace_name': 'workspace',
            'list_view_type': 'All',
        }

    def test_machine_learning_schedule_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'find-sub-daily-machine-learning-schedules',
                'resource': 'azure.machine-learning-schedule',
                'filters': [
                    {'type': 'value', 'key': 'properties.isEnabled', 'value': True},
                    {
                        'type': 'value',
                        'key': 'properties.trigger.frequency',
                        'op': 'in',
                        'value': ['Minute', 'Hour'],
                    },
                ],
            }, validate=True)
        assert p

        for action in ('tag', 'untag', 'auto-tag-user', 'auto-tag-date',
                       'tag-trim', 'mark-for-op'):
            assert action not in MachineLearningSchedule.action_registry
        assert 'marked-for-op' not in MachineLearningSchedule.filter_registry
        assert 'diagnostic-settings' not in MachineLearningSchedule.filter_registry

    @arm_template('machine-learning-schedule.json')
    @cassette_name('machine-learning-schedules')
    def test_machine_learning_schedule_query(self):
        p = self.load_policy({
            'name': 'find-all-machine-learning-schedules',
            'resource': 'azure.machine-learning-schedule',
        })
        resources = p.run()

        assert {r['name']: r['properties']['isEnabled'] for r in resources} == {
            'cctest-schedule-minute': False,
            'cctest-schedule-yearly': True,
        }
        minute = next(r for r in resources if r['name'] == 'cctest-schedule-minute')
        assert minute['properties']['trigger']['triggerType'] == 'Recurrence'
        assert minute['properties']['trigger']['frequency'] == 'Minute'
        assert minute['properties']['trigger']['interval'] == 1

        yearly = next(r for r in resources if r['name'] == 'cctest-schedule-yearly')
        assert yearly['properties']['trigger']['triggerType'] == 'Cron'
        assert yearly['properties']['trigger']['expression'] == '0 0 1 1 *'

        for r in resources:
            assert r['properties']['action']['actionType'] == 'CreateJob'
            assert r['id'].lower().startswith(r['c7n:parent-id'].lower() + '/schedules/')

    @arm_template('machine-learning-schedule.json')
    @cassette_name('machine-learning-schedules')
    def test_machine_learning_schedule_filter(self):
        p = self.load_policy({
            'name': 'find-disabled-minute-machine-learning-schedules',
            'resource': 'azure.machine-learning-schedule',
            'filters': [
                {'type': 'value', 'key': 'properties.isEnabled', 'value': False},
                {'type': 'value', 'key': 'properties.action.actionType', 'value': 'CreateJob'},
                {'type': 'value', 'key': 'properties.trigger.triggerType', 'value': 'Recurrence'},
                {
                    'type': 'value',
                    'key': 'properties.trigger.frequency',
                    'op': 'in',
                    'value': ['Minute', 'Hour'],
                },
            ],
        })
        resources = p.run()

        assert [r['name'] for r in resources] == ['cctest-schedule-minute']

    def test_machine_learning_schedule_skips_missing_workspace(self):
        schedule = Schedule(
            properties=ScheduleProperties(
                action=JobScheduleAction(
                    job_definition=CommandJob(command='echo hello', environment_id='env')
                ),
                trigger=RecurrenceTrigger(frequency='Minute', interval=1),
                is_enabled=True,
            )
        )
        schedule.id = WORKSPACE_ID.format('live') + '/schedules/every-minute'
        schedule.name = 'every-minute'

        def list_schedules(workspace_name, **kwargs):
            if workspace_name == 'gone':
                raise ResourceNotFoundError('ParentResourceNotFound')
            return [schedule]

        client = Mock()
        client.schedules.list.side_effect = list_schedules

        resources = self._manager(client, ['gone', 'live']).resources()

        assert [r['id'] for r in resources] == [schedule.id]
        assert resources[0]['c7n:parent-id'] == WORKSPACE_ID.format('live')
        assert resources[0]['properties']['trigger']['frequency'] == 'Minute'
        client.schedules.list.assert_any_call(
            resource_group_name='VV',
            workspace_name='live',
            list_view_type='All',
        )

    def test_machine_learning_schedule_raises_other_errors(self):
        client = Mock()
        client.schedules.list.side_effect = HttpResponseError('Forbidden')

        manager = self._manager(client, ['live'])

        with pytest.raises(HttpResponseError):
            manager.resources()

    def _manager(self, client, workspace_names):
        parent_manager = Mock()
        parent_manager.resource_type.id = 'id'
        parent_manager.resources.return_value = [{
            'id': WORKSPACE_ID.format(name),
            'name': name,
            'resourceGroup': 'VV',
        } for name in workspace_names]

        p = self.load_policy({
            'name': 'find-all-machine-learning-schedules',
            'resource': 'azure.machine-learning-schedule',
        })
        manager = p.resource_manager
        manager.get_parent_manager = Mock(return_value=parent_manager)
        manager.get_client = Mock(return_value=client)
        return manager
