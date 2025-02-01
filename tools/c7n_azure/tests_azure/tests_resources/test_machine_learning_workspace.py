from ..azure_common import BaseTest


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
