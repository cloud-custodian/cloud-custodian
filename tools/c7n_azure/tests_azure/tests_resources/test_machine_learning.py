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
