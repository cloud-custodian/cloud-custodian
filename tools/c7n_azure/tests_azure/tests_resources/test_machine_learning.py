from datetime import datetime, timezone
from unittest.mock import Mock

from azure.mgmt.machinelearningservices.models import (
    DataContainer,
    DataContainerProperties,
    SystemData
)

from ..azure_common import BaseTest, arm_template, cassette_name


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
            workspace_name='vvmlwrkspc'
        )
        assert len(resources) == 1
        assert resources[0]['id'] == data_container_id
        assert resources[0]['resourceGroup'] == 'VV'
        assert resources[0]['c7n:parent-id'] == parent_id
        assert resources[0]['properties']['isArchived'] is False
        assert resources[0]['systemData']['lastModifiedAt'] == '2024-01-02T00:00:00.000Z'
