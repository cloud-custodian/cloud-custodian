from datetime import datetime, timezone
from unittest.mock import Mock

from azure.mgmt.machinelearningservices.models import (
    DataContainer,
    DataContainerProperties,
    SystemData,
)

from ..azure_common import BaseTest, arm_template, cassette_name


# Machine Learning workspace
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


# Online endpoint resource tests
class MachineLearningOnlineEndpointTest(BaseTest):

    def test_machine_learning_online_endpoint_schema_validate(self):
        with self.sign_out_patch():
            policy = self.load_policy({
                'name': 'machine-learning-online-endpoints',
                'resource': 'azure.machine-learning-online-endpoint',
            }, validate=True)

        assert policy

    @arm_template('machine-learning-online-deployment.json')
    @cassette_name('machine-learning-online-endpoint-query')
    def test_machine_learning_online_endpoint_query(self):
        policy = self.load_policy({
            'name': 'machine-learning-online-endpoint-query',
            'resource': 'azure.machine-learning-online-endpoint',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'value': 'cctest-ml-*',
                'op': 'glob',
            }],
        })

        resources = policy.run()

        assert len(resources) == 1
        assert resources[0]['name'].startswith('cctest-ml-')
        assert '/workspaces/' in resources[0]['c7n:parent-id']

    @arm_template('machine-learning-online-deployment.json')
    @cassette_name('machine-learning-online-endpoint-deployment-count')
    def test_machine_learning_online_endpoint_deployment_count(self):
        policy = self.load_policy({
            'name': 'machine-learning-online-endpoint-deployment-count',
            'resource': 'azure.machine-learning-online-endpoint',
            'filters': [{
                'type': 'online-deployments',
                'attrs': [{
                    'type': 'value',
                    'key': 'properties.model',
                    'value': 'present',
                }],
                'count': 1,
            }],
        })

        resources = policy.run()

        assert len(resources) == 1
        assert resources[0]['name'].startswith('cctest-ml-')


# Online deployment resource tests
class MachineLearningOnlineDeploymentTest(BaseTest):

    def test_machine_learning_online_deployment_schema_validate(self):
        with self.sign_out_patch():
            policy = self.load_policy({
                'name': 'machine-learning-online-deployments',
                'resource': 'azure.machine-learning-online-deployment',
                'filters': [{
                    'type': 'value',
                    'key': 'properties.model',
                    'value': 'azureml:model-a:12',
                }],
            }, validate=True)

        assert policy

    @arm_template('machine-learning-online-deployment.json')
    @cassette_name('machine-learning-online-deployment-query')
    def test_machine_learning_online_deployment_query(self):
        policy = self.load_policy({
            'name': 'machine-learning-online-deployment-query',
            'resource': 'azure.machine-learning-online-deployment',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'value': 'blue',
            }],
        })

        resources = policy.run()

        assert len(resources) == 1
        assert resources[0]['name'] == 'blue'
        assert resources[0]['properties']['model']
        assert '/onlineEndpoints/cctest-ml-' in resources[0]['c7n:parent-id']


class MachineLearningDataContainerTest(BaseTest):

    def test_machine_learning_data_container_schema_validate(self):
        with self.sign_out_patch():
            policy = self.load_policy({
                'name': 'find-all-machine-learning-data-containers',
                'resource': 'azure.machine-learning-data-container',
                'filters': [{'type': 'value', 'key': 'properties.isArchived', 'value': False}],
            }, validate=True)
        assert policy

    @arm_template('machine-learning.json')
    @cassette_name('machine-learning-data-container')
    def test_machine_learning_data_container_policy_run(self):
        policy = self.load_policy({
            'name': 'find-cctest-machine-learning-data-containers',
            'resource': 'azure.machine-learning-data-container',
            'filters': [
                {'type': 'value', 'key': 'name', 'value': 'cctest-ml-data-container'},
                {'type': 'value', 'key': 'properties.isArchived', 'value': False},
            ],
        })
        resources = policy.run()
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
        data_container = DataContainer(
            properties=DataContainerProperties(data_type='uri_file', is_archived=False)
        )
        data_container.id = '{}/data/dataset-one'.format(parent_id)
        data_container.name = 'dataset-one'
        data_container.type = 'Microsoft.MachineLearningServices/workspaces/data'
        data_container.system_data = SystemData(
            last_modified_at=datetime(2024, 1, 2, tzinfo=timezone.utc)
        )
        parent_manager = Mock()
        parent_manager.resource_type.id = 'id'
        parent_manager.resources.return_value = [{
            'id': parent_id, 'name': 'vvmlwrkspc', 'resourceGroup': 'VV',
        }]
        client = Mock()
        client.data_containers.list.return_value = [data_container]
        policy = self.load_policy({
            'name': 'find-all-machine-learning-data-containers',
            'resource': 'azure.machine-learning-data-container',
        })
        manager = policy.resource_manager
        manager.get_parent_manager = Mock(return_value=parent_manager)
        manager.get_client = Mock(return_value=client)

        resources = manager.resources()

        client.data_containers.list.assert_called_once_with(
            resource_group_name='VV', workspace_name='vvmlwrkspc'
        )
        assert len(resources) == 1
        assert resources[0]['id'] == data_container.id
        assert resources[0]['resourceGroup'] == 'VV'
        assert resources[0]['c7n:parent-id'] == parent_id
        assert resources[0]['properties']['isArchived'] is False
        assert resources[0]['systemData']['lastModifiedAt'] == '2024-01-02T00:00:00.000Z'
