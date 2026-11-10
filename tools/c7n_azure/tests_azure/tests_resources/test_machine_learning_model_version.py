# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import copy
from unittest import mock

import jsonschema
from azure.mgmt.machinelearningservices import models
from parameterized import parameterized

from c7n import policy
from c7n.exceptions import PolicyExecutionError

from ..azure_common import BaseTest, arm_template, strict_cassette


class MachineLearningModelVersionTest(BaseTest):

    def test_machine_learning_model_version_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'find-all-machine-learning-model-versions',
                'resource': 'azure.machine-learning-model-version'
            }, validate=True)
            self.assertTrue(p)

    def test_machine_learning_model_version_update_schema(self) -> None:
        with self.sign_out_patch():
            policy = self.load_policy({
                'name': 'archive-model-version',
                'resource': 'azure.machine-learning-model-version',
                'actions': [{
                    'type': 'update',
                    'properties': {'isArchived': True},
                }],
            }, validate=True)
        schema = policy.resource_manager.actions[0].schema
        for properties in (
            {'description': 'Retired model'},
            {'tags': {'owner': 'ml-team'}},
            {'properties': {'reviewed': 'true'}},
            {'isArchived': False},
            {'stage': 'Production'},
        ):
            with self.subTest(properties=properties):
                jsonschema.validate({'type': 'update', 'properties': properties}, schema)

        for action in (
            {'type': 'update'},
            {'type': 'update', 'properties': {}},
            {'type': 'update', 'properties': {'provisioningState': 'Succeeded'}},
            {'type': 'update', 'properties': {'isArchived': 'true'}},
            {'type': 'update', 'properties': {'tags': {'owner': 42}}},
            {'type': 'update', 'properties': {'isAnonymous': True}},
            {'type': 'update', 'properties': {'flavors': {}}},
            {'type': 'update', 'properties': {'jobName': 'job'}},
            {'type': 'update', 'properties': {'modelType': 'mlflow_model'}},
            {'type': 'update', 'properties': {'modelUri': 'different-path'}},
            {'type': 'update', 'properties': {'properties': {'key': 42}}},
        ):
            with self.subTest(action=action), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(action, schema)

    def test_machine_learning_model_version_update_preserves_properties(self) -> None:
        with self.sign_out_patch():
            policy = self.load_policy({
                'name': 'update-model-version',
                'resource': 'azure.machine-learning-model-version',
                'actions': [{
                    'type': 'update',
                    'properties': {
                        'isArchived': True,
                        'tags': {'owner': 'new-owner'},
                        'properties': {'keep': 'value', 'added': 'value'},
                    },
                }],
            }, validate=True)
        resource = {
            'id': '/subscriptions/sub/resourceGroups/rg/providers/'
                  'Microsoft.MachineLearningServices/workspaces/ws/models/model/versions/7',
            'name': '7',
            'properties': {'description': 'stale enumeration'},
            'c7n:parent-id': 'workspace-annotation',
        }
        original = copy.deepcopy(resource)
        current = models.ModelVersion.deserialize({
            'id': resource['id'],
            'name': '7',
            'type': 'Microsoft.MachineLearningServices/workspaces/models/versions',
            'systemData': {'createdBy': 'creator'},
            'properties': {
                'description': 'fresh description',
                'modelUri': 'azureml://datastores/store/paths/model',
                'modelType': 'custom_model',
                'isArchived': False,
                'isAnonymous': False,
                'tags': {'owner': 'old-owner', 'remove': 'yes'},
                'properties': {'keep': 'value'},
                'provisioningState': 'Succeeded',
                'stage': 'Development',
            },
        })
        action = policy.resource_manager.actions[0]
        client = mock.Mock()
        client.model_versions.get.return_value = current
        with mock.patch.object(policy.resource_manager, 'get_client', return_value=client):
            action._prepare_processing()
            action._process_resource(resource)
        arguments = {
            'resource_group_name': 'rg',
            'workspace_name': 'ws',
            'name': 'model',
            'version': '7',
        }
        client.model_versions.get.assert_called_once_with(**arguments)
        client.model_versions.create_or_update.assert_called_once_with(
            **arguments,
            body=current,
        )
        self.assertEqual({
            'properties': {
                'description': 'fresh description',
                'modelUri': 'azureml://datastores/store/paths/model',
                'modelType': 'custom_model',
                'isArchived': True,
                'isAnonymous': False,
                'tags': {'owner': 'new-owner'},
                'properties': {'keep': 'value', 'added': 'value'},
                'stage': 'Development',
            },
        }, current.serialize())
        self.assertEqual(original, resource)

    def test_machine_learning_model_version_update_rejects_property_changes(self) -> None:
        with self.sign_out_patch():
            policy = self.load_policy({
                'name': 'reject-property-changes',
                'resource': 'azure.machine-learning-model-version',
                'actions': [{
                    'type': 'update',
                    'properties': {'properties': {'keep': 'changed'}},
                }],
            }, validate=True)
        action = policy.resource_manager.actions[0]
        client = mock.Mock()
        client.model_versions.get.return_value = models.ModelVersion(
            properties=models.ModelVersionProperties(properties={'keep': 'original'}),
        )
        with mock.patch.object(policy.resource_manager, 'get_client', return_value=client):
            action._prepare_processing()
            with self.assertRaisesRegex(PolicyExecutionError, 'keep'):
                action._process_resource({
                    'id': '/subscriptions/sub/resourceGroups/rg/providers/'
                          'Microsoft.MachineLearningServices/workspaces/ws/'
                          'models/model/versions/1',
                })
        client.model_versions.create_or_update.assert_not_called()

    @arm_template('machine-learning-model-version.json')
    def test_machine_learning_model_version_query(self):
        p = self.load_policy({
            'name': 'find-all-machine-learning-model-versions',
            'resource': 'azure.machine-learning-model-version',
        })
        resources = p.run()
        self.assertEqual(2, len(resources))
        self.assertTrue(all('/models/cctest-model/versions/' in r['id'] for r in resources))
        self.assertTrue(all('c7n:parent-id' in r for r in resources))

    @arm_template('machine-learning-model-version.json')
    def test_machine_learning_model_version_filter_archived(self):
        p = self.load_policy({
            'name': 'find-archived-model-versions',
            'resource': 'azure.machine-learning-model-version',
            'filters': [{
                'type': 'value',
                'key': 'properties.isArchived',
                'value': True
            }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('2', resources[0]['name'])

    @arm_template('machine-learning-model-version.json')
    def test_machine_learning_model_version_filter_anonymous(self):
        p = self.load_policy({
            'name': 'find-anonymous-model-versions',
            'resource': 'azure.machine-learning-model-version',
            'filters': [{
                'type': 'value',
                'key': 'properties.isAnonymous',
                'value': True
            }],
        })
        resources = p.run()
        self.assertEqual(2, len(resources))
        self.assertTrue(all(r['properties']['isAnonymous'] for r in resources))
        self.assertEqual({'2', '3'}, {r['name'] for r in resources})


class MachineLearningModelVersionUpdateTest(BaseTest):
    recording_resource_group = 'test_machine-learning-model-version-update'

    @parameterized.expand(
        [
            ('description', 'Updated description'),
            ('tags', {'owner': 'updated'}),
            ('properties', {'approved': 'true'}),
            ('isArchived', True),
            ('stage', 'Production'),
        ],
        name_func=lambda func, number, param: f'{func.__name__}_{param.args[0]}',
    )
    @arm_template('machine-learning-model-version-update.json')
    @strict_cassette(None)
    def test_update(self, field: str, value: str | bool | dict) -> None:
        model_name = f'cctest-update-{field.lower()}'
        policy_data = {
            'name': f'update-model-version-{field.lower()}',
            'resource': 'azure.machine-learning-model-version',
            'filters': [
                {'resourceGroup': self.recording_resource_group},
                {
                    'type': 'value',
                    'key': 'id',
                    'op': 'glob',
                    'value': f'*/models/{model_name}/versions/1',
                },
                {'properties.isAnonymous': False},
                {'properties.isArchived': False},
            ],
        }
        discovery = self._load_scoped_policy(policy_data)
        resources = discovery.run()
        self.assertEqual(1, len(resources))
        resource = resources[0]
        client = discovery.resource_manager.get_client()
        arguments = {
            'resource_group_name': self.recording_resource_group,
            'workspace_name': resource['c7n:parent-id'].rsplit('/', 1)[1],
            'name': model_name,
            'version': '1',
        }
        before = client.model_versions.get(**arguments).properties.serialize()
        self.assertNotEqual(value, before.get(field))
        policy_data['actions'] = [{
            'type': 'update',
            'properties': {field: value},
        }]
        policy = self._load_scoped_policy(policy_data)
        self.assertEqual(1, len(policy.run()))
        after = client.model_versions.get(**arguments).properties.serialize()
        expected = before.copy()
        expected[field] = {**before[field], **value} if field == 'properties' else value
        if field == 'isArchived':
            expected['stage'] = 'Archived'
        self.assertEqual(expected, after)
        if field == 'isArchived':
            self.assertEqual([], discovery.run())

    @arm_template('machine-learning-model-version-update.json')
    @strict_cassette('update-properties-reject-change')
    def test_update_properties_reject_change(self) -> None:
        data = {
            'name': 'reject-changing-model-properties',
            'resource': 'azure.machine-learning-model-version',
            'filters': [{
                'type': 'value',
                'key': 'id',
                'op': 'glob',
                'value': '*/models/cctest-update-properties/versions/1',
            }],
        }
        discovery = self._load_scoped_policy(data)
        resources = discovery.run()
        self.assertEqual(1, len(resources))
        arguments = {
            'resource_group_name': self.recording_resource_group,
            'workspace_name': resources[0]['c7n:parent-id'].rsplit('/', 1)[1],
            'name': 'cctest-update-properties',
            'version': '1',
        }
        client = discovery.resource_manager.get_client()
        before = client.model_versions.get(**arguments).properties.serialize()
        data['actions'] = [{
            'type': 'update',
            'properties': {'properties': {'reviewed': 'true'}},
        }]
        with self.assertRaisesRegex(PolicyExecutionError, 'reviewed'):
            self._load_scoped_policy(data).run()
        after = client.model_versions.get(**arguments).properties.serialize()
        self.assertEqual(before, after)

    def _load_scoped_policy(self, data: dict) -> policy.Policy:
        policy = self.load_policy(data, validate=True)
        manager = policy.resource_manager
        manager.parent_manager = manager.get_resource_manager(
            'machine-learning-workspace',
            {'filters': [{'resourceGroup': self.recording_resource_group}]},
        )
        return policy
