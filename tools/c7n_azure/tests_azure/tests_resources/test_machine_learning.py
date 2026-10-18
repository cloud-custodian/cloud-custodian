from datetime import datetime, timezone
from unittest.mock import Mock

from azure.core.exceptions import ResourceNotFoundError
from azure.mgmt.machinelearningservices.models import (
    DataContainer,
    DataContainerProperties,
    SystemData
)

from c7n.utils import local_session
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser
from ..azure_common import (
    BaseTest,
    arm_template,
    cassette_name,
    strict_cassette,
    )


class MachineLearningWorkspaceTest(BaseTest):

    def test_machine_learning_workspace_schema_validate(self):
        p = self.load_policy({
            'name': 'find-all-machine-learning-workspaces',
            'resource': 'azure.machine-learning-workspace'
        }, validate=True)
        self.assertTrue(p)

    def test_machine_learning_workspace_policy_run(self):
        p = self.load_policy({
            'name': 'find-all-machine-learning-workspaces',
            'resource': 'azure.machine-learning-workspace',
            'filters': [{
                'type': 'value',
                'key': 'properties.privateEndpointConnections[].properties'
                       '.privateLinkServiceConnectionState.status',
                'value': 'Approved',
                'op': 'contains'
            }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('mlvvtest', resources[0]['name'])


class MachineLearningWorkspaceComputeInstancesFilterTest(BaseTest):

    def test_query(self):
        p = self.load_policy({
            'name': 'compute',
            'resource': 'azure.machine-learning-workspace',
            'filters': [{
                'type': 'compute-instances',
                'attrs': [{
                    'type': 'value',
                    'key': 'properties.properties.scaleSettings.minNodeCount',
                    'value': 0
                }]
            }],
        })
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('vvmlwrkspc', resources[0]['name'])

    def test_additional_attributes(self):
        p = self.load_policy({
            'name': 'compute',
            'resource': 'azure.machine-learning-workspace',
            'filters': [{
                'type': 'compute-instances',
                'attrs': [{
                    'type': 'value',
                    'key': 'properties.properties.idleTimeBeforeShutdown',
                    'value': 'PT120M'
                }]
            }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]['c7n:ComputeInstances'][0]['name'], 'vvmlwrkspc11')


class MachineLearningWorkspaceResourceLockFilterTest(BaseTest):

    def test_query(self):
        p = self.load_policy({
            'name': 'compute',
            'resource': 'azure.machine-learning-workspace',
            'filters': [{
                'type': 'resource-lock',
                'lock-type': 'ReadOnly'
            }],
        })
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('mlwsp165red', resources[0]['name'])


class MachineLearningDataContainerTest(BaseTest):

    def test_machine_learning_data_container_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'find-all-machine-learning-data-containers',
                'resource': 'azure.machine-learning-data-container',
                'filters': [{
                    'type': 'value',
                    'key': 'properties.isArchived',
                    'value': False
                }]
            }, validate=True)
            assert p

            p = self.load_policy({
                'name': 'archive-machine-learning-data-containers',
                'resource': 'azure.machine-learning-data-container',
                'actions': [{'type': 'archive'}]
            }, validate=True)
            assert p

    @arm_template('machine-learning.json')
    @cassette_name('machine-learning-data-container')
    def test_machine_learning_data_container_policy_run(self):
        p = self.load_policy({
            'name': 'find-cctest-machine-learning-data-containers',
            'resource': 'azure.machine-learning-data-container',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'value': 'cctest-ml-data-container'
            }, {
                'type': 'value',
                'key': 'properties.isArchived',
                'value': False
            }]
        })
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['name'] == 'cctest-ml-data-container'
        assert resources[0]['type'] == 'Microsoft.MachineLearningServices/workspaces/data'
        assert '/workspaces/' in resources[0]['id'].lower()
        assert '/data/' in resources[0]['id'].lower()
        assert resources[0]['properties']['isArchived'] is False
        assert 'systemData' in resources[0]

    @arm_template('machine-learning-data-container-archive.json')
    @strict_cassette('machine-learning-data-container-archive')
    def test_machine_learning_data_container_archive(self):
        p = self.load_policy({
            'name': 'archive-stale-ml-data-containers',
            'resource': 'azure.machine-learning-data-container',
            'filters': [{
                'type': 'value',
                'key': 'resourceGroup',
                'value': 'test_machine-learning-data-container-archive'
            }],
            'actions': [{'type': 'archive'}]
        }, validate=True, session_factory=Session)

        resources = p.run()
        assert sorted(r['name'] for r in resources) == [
            'cctest-dc-active',
            'cctest-dc-archived',
            ]

        active = next(r for r in resources if r['name'] == 'cctest-dc-active')
        client = local_session(Session).client(
            'azure.mgmt.machinelearningservices.MachineLearningServicesMgmtClient')
        container = client.data_containers.get(
            active['resourceGroup'],
            ResourceIdParser.get_resource_name(active['c7n:parent-id']),
            active['name'],
            )
        assert container.properties.is_archived

    @arm_template('machine-learning-data-container-archive.json')
    @cassette_name('machine-learning-data-container-archived-included')
    def test_machine_learning_data_container_query_includes_archived(self):
        p = self.load_policy({
            'name': 'find-cctest-archive-fixture-data-containers',
            'resource': 'azure.machine-learning-data-container',
            'filters': [{
                'type': 'value',
                'key': 'resourceGroup',
                'value': 'test_machine-learning-data-container-archive'
            }]
        })
        resources = p.run()
        assert {
            r['name']: r['properties']['isArchived']
            for r in resources
            } == {
                'cctest-dc-active': False,
                'cctest-dc-archived': True,
                }

    def test_machine_learning_data_container_child_query(self):
        parent_id = (
            '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/VV'
            '/providers/Microsoft.MachineLearningServices/workspaces/vvmlwrkspc'
        )
        data_container_id = '{}/data/dataset-one'.format(parent_id)

        data_container = DataContainer(
            properties=DataContainerProperties(
                data_type='uri_file',
                is_archived=False
            )
        )
        data_container.id = data_container_id
        data_container.name = 'dataset-one'
        data_container.type = 'Microsoft.MachineLearningServices/workspaces/data'
        data_container.system_data = SystemData(
            last_modified_at=datetime(2024, 1, 2, tzinfo=timezone.utc)
        )

        parent_manager = Mock()
        parent_manager.resource_type.id = 'id'
        parent_manager.resources.return_value = [{
            'id': parent_id,
            'name': 'vvmlwrkspc',
            'resourceGroup': 'VV'
        }]

        client = Mock()
        client.data_containers.list.return_value = [data_container]

        p = self.load_policy({
            'name': 'find-all-machine-learning-data-containers',
            'resource': 'azure.machine-learning-data-container'
        })
        manager = p.resource_manager
        manager.get_parent_manager = Mock(return_value=parent_manager)
        manager.get_client = Mock(return_value=client)

        resources = manager.resources()

        client.data_containers.list.assert_called_once_with(
            resource_group_name='VV',
            workspace_name='vvmlwrkspc',
            list_view_type='All',
        )
        assert len(resources) == 1
        assert resources[0]['id'] == data_container_id
        assert resources[0]['resourceGroup'] == 'VV'
        assert resources[0]['c7n:parent-id'] == parent_id
        assert resources[0]['properties']['isArchived'] is False
        assert resources[0]['systemData']['lastModifiedAt'] == '2024-01-02T00:00:00.000Z'


class MachineLearningWorkspaceChildTest(BaseTest):

    workspace_base_id = (
        '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/{0}'
        '/providers/Microsoft.MachineLearningServices/workspaces/{1}'
    )

    def _workspace(self, name, resource_group='VV', provisioning_state='Succeeded'):
        return {
            'id': self.workspace_base_id.format(resource_group, name),
            'name': name,
            'resourceGroup': resource_group,
            'properties': {'provisioningState': provisioning_state},
        }

    def _manager(self, resource, workspaces, client):
        parent_manager = Mock()
        parent_manager.resource_type.id = 'id'
        parent_manager.resources.return_value = workspaces

        policy = self.load_policy({'name': 'ml-workspace-children', 'resource': resource})
        manager = policy.resource_manager
        manager.get_parent_manager = Mock(return_value=parent_manager)
        manager.get_client = Mock(return_value=client)
        return manager

    def _data_container(self, workspace):
        data_container = DataContainer(properties=DataContainerProperties(data_type='uri_file'))
        data_container.id = '{}/data/dataset-one'.format(workspace['id'])
        data_container.name = 'dataset-one'
        return data_container

    def test_skips_deleting_workspace(self):
        healthy = self._workspace('healthy')
        deleting = self._workspace('deleting', 'gone-rg', provisioning_state='Deleting')
        client = Mock()
        client.data_containers.list.return_value = [self._data_container(healthy)]
        manager = self._manager(
            'azure.machine-learning-data-container', [deleting, healthy], client)

        with self.assertLogs('custodian.azure.machine_learning', level='WARNING') as logs:
            resources = manager.resources()

        client.data_containers.list.assert_called_once_with(
            resource_group_name='VV', workspace_name='healthy', list_view_type='All')
        assert [r['c7n:parent-id'] for r in resources] == [healthy['id']]
        assert deleting['id'] in logs.output[0]

    def test_skips_workspace_not_found(self):
        healthy = self._workspace('healthy')
        missing = self._workspace('missing', 'gone-rg')

        def list_data_containers(resource_group_name, workspace_name, **kwargs):
            if workspace_name == 'missing':
                raise ResourceNotFoundError('ParentResourceNotFound')
            return [self._data_container(healthy)]

        client = Mock()
        client.data_containers.list.side_effect = list_data_containers
        manager = self._manager(
            'azure.machine-learning-data-container', [missing, healthy], client)

        with self.assertLogs('custodian.azure.machine_learning', level='WARNING') as logs:
            resources = manager.resources()

        assert client.data_containers.list.call_count == 2
        assert [r['c7n:parent-id'] for r in resources] == [healthy['id']]
        assert missing['id'] in logs.output[0]

    def test_model_version_skips_deleting_workspace(self):
        healthy = self._workspace('healthy')
        deleting = self._workspace('deleting', 'gone-rg', provisioning_state='Deleting')
        container = Mock()
        container.name = 'model-one'
        version = Mock()
        version.serialize.return_value = {
            'id': '{}/models/model-one/versions/1'.format(healthy['id']),
            'name': '1',
        }
        client = Mock()
        client.model_containers.list.return_value = [container]
        client.model_versions.list.return_value = [version]
        manager = self._manager(
            'azure.machine-learning-model-version', [deleting, healthy], client)

        with self.assertLogs('custodian.azure.machine_learning', level='WARNING'):
            resources = manager.resources()

        client.model_containers.list.assert_called_once_with(
            resource_group_name='VV', workspace_name='healthy')
        assert [r['c7n:parent-id'] for r in resources] == [healthy['id']]
