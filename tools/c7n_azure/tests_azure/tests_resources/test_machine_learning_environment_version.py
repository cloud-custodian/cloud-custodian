# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import Mock

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.mgmt.machinelearningservices.models import (
    EnvironmentVersion,
    EnvironmentVersionProperties,
)

from ..azure_common import BaseTest, arm_template, cassette_name

RESOURCE_GROUP = 'test_machine-learning-environment-version'


def only_ours(resources):
    return [r for r in resources if f'/resourcegroups/{RESOURCE_GROUP}/' in r['id'].lower()]


def environment_and_version(resource):
    environment, version = resource['id'].split('/environments/')[1].split('/versions/')
    return environment, version


class MachineLearningEnvironmentVersionTest(BaseTest):

    def test_machine_learning_environment_version_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'find-all-machine-learning-environment-versions',
                'resource': 'azure.machine-learning-environment-version',
            }, validate=True)
        assert p

    @arm_template('machine-learning-environment-version.json')
    @cassette_name('machine-learning-environment-versions')
    def test_machine_learning_environment_version_query(self):
        p = self.load_policy({
            'name': 'find-user-machine-learning-environment-versions',
            'resource': 'azure.machine-learning-environment-version',
            'filters': [
                {'type': 'value', 'key': 'properties.environmentType', 'value': 'UserCreated'},
            ],
        })
        resources = only_ours(p.run())
        assert {environment_and_version(r) for r in resources} == {
            ('cctest-env', '1'),
            ('cctest-env', '2'),
            ('cctest-archived-env', '1'),
        }
        assert all('c7n:parent-id' in r for r in resources)

    @arm_template('machine-learning-environment-version.json')
    @cassette_name('machine-learning-environment-versions')
    def test_machine_learning_environment_version_filter_archived(self):
        p = self.load_policy({
            'name': 'find-archived-machine-learning-environment-versions',
            'resource': 'azure.machine-learning-environment-version',
            'filters': [
                {'type': 'value', 'key': 'properties.environmentType', 'value': 'UserCreated'},
                {'type': 'value', 'key': 'properties.isArchived', 'value': True},
            ],
        })
        resources = only_ours(p.run())
        assert [environment_and_version(r) for r in resources] == [('cctest-env', '2')]

    def test_machine_learning_environment_version_skips_missing_versions(self):
        parent_id = (
            '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/VV'
            '/providers/Microsoft.MachineLearningServices/workspaces/vvmlwrkspc'
        )
        version_id = f'{parent_id}/environments/cctest-env/versions/2'

        version = EnvironmentVersion(
            properties=EnvironmentVersionProperties(
                image='mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest',
                is_archived=True
            )
        )
        version.id = version_id
        version.name = '2'

        curated, user_created = Mock(), Mock()
        curated.name = 'AzureML-Triton'
        user_created.name = 'cctest-env'

        def list_versions(name, **kwargs):
            if name == 'AzureML-Triton':
                raise ResourceNotFoundError('Not Found')
            return [version]

        client = Mock()
        client.environment_containers.list.return_value = [curated, user_created]
        client.environment_versions.list.side_effect = list_versions

        parent_manager = Mock()
        parent_manager.resource_type.id = 'id'
        parent_manager.resources.return_value = [{
            'id': parent_id,
            'name': 'vvmlwrkspc',
            'resourceGroup': 'VV'
        }]

        p = self.load_policy({
            'name': 'find-all-machine-learning-environment-versions',
            'resource': 'azure.machine-learning-environment-version'
        })
        manager = p.resource_manager
        manager.get_parent_manager = Mock(return_value=parent_manager)
        manager.get_client = Mock(return_value=client)

        resources = manager.resources()

        assert [r['id'] for r in resources] == [version_id]
        assert resources[0]['properties']['isArchived'] is True
        assert resources[0]['c7n:parent-id'] == parent_id
        client.environment_containers.list.assert_called_once_with(
            resource_group_name='VV',
            workspace_name='vvmlwrkspc',
            list_view_type='All'
        )
        client.environment_versions.list.assert_any_call(
            resource_group_name='VV',
            workspace_name='vvmlwrkspc',
            name='cctest-env',
            list_view_type='All'
        )

    def test_machine_learning_environment_version_skips_missing_workspace(self):
        client = Mock()
        client.environment_containers.list.side_effect = ResourceNotFoundError(
            'ResourceGroupNotFound')

        manager = self._manager_with_client(client)

        assert manager.resources() == []

    def test_machine_learning_environment_version_raises_other_errors(self):
        user_created = Mock()
        user_created.name = 'cctest-env'

        client = Mock()
        client.environment_containers.list.return_value = [user_created]
        client.environment_versions.list.side_effect = HttpResponseError('Forbidden')

        manager = self._manager_with_client(client)

        with self.assertRaises(HttpResponseError):
            manager.resources()

    def _manager_with_client(self, client):
        parent_manager = Mock()
        parent_manager.resource_type.id = 'id'
        parent_manager.resources.return_value = [{
            'id': (
                '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/VV'
                '/providers/Microsoft.MachineLearningServices/workspaces/vvmlwrkspc'
            ),
            'name': 'vvmlwrkspc',
            'resourceGroup': 'VV'
        }]

        p = self.load_policy({
            'name': 'find-all-machine-learning-environment-versions',
            'resource': 'azure.machine-learning-environment-version'
        })
        manager = p.resource_manager
        manager.get_parent_manager = Mock(return_value=parent_manager)
        manager.get_client = Mock(return_value=client)
        return manager
