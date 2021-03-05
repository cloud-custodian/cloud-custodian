# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import os
import sys
import time

import pytest

from c7n_gcp.resources.resourcemanager import HierarchyAction
from gcp_common import BaseTest
from mock import mock

from c7n.exceptions import ResourceLimitExceeded


class LimitsTest(BaseTest):
    def test_policy_resource_limits(self):
        parent = 'organizations/926683928810'
        session_factory = self.replay_flight_data('folder-query')

        p = self.load_policy(
            {'name': 'limits',
             "max-resources-percent": 2.5,
             'resource': 'gcp.folder',
             'query':
                 [{'parent': parent}]},
            session_factory=session_factory)

        p.ctx.metrics.flush = mock.MagicMock()
        output = self.capture_logging('custodian.policy', level=logging.ERROR)
        self.assertRaises(ResourceLimitExceeded, p.run)
        self.assertTrue("policy:limits exceeded resource-limit:2.5% found:1 total:"
                        in output.getvalue())
        self.assertEqual(
            p.ctx.metrics.buf[0]['MetricName'], 'ResourceLimitExceeded')

    def test_policy_resource_limits_count(self):
        session_factory = self.replay_flight_data('disk-query')
        p = self.load_policy(
            {'name': 'limits',
             'resource': 'gcp.disk',
             'max-resources': 1},
            session_factory=session_factory)

        p.ctx.metrics.flush = mock.MagicMock()
        output = self.capture_logging('custodian.policy', level=logging.ERROR)
        self.assertRaises(ResourceLimitExceeded, p.run)
        self.assertTrue("policy:limits exceeded resource-limit:1 found:"
                        in output.getvalue())
        self.assertEqual(
            p.ctx.metrics.buf[0]['MetricName'], 'ResourceLimitExceeded')


class OrganizationTest(BaseTest):

    def test_organization_query(self):
        organization_name = 'organizations/851339424791'
        session_factory = self.replay_flight_data('organization-query')

        policy = self.load_policy(
            {'name': 'gcp-organization-dryrun',
             'resource': 'gcp.organization'},
            session_factory=session_factory)

        organization_resources = policy.run()
        self.assertEqual(organization_resources[0]['name'], organization_name)

    def test_organization_set_iam_policy(self):
        resource_full_name = 'organizations/926683928810'
        get_iam_policy_params = {'resource': resource_full_name, 'body': {}}
        session_factory = self.replay_flight_data('organization-set-iam-policy')

        policy = self.load_policy(
            {'name': 'gcp-organization-set-iam-policy',
             'resource': 'gcp.organization',
             'filters': [{'type': 'value',
                          'key': 'name',
                          'value': resource_full_name}],
             'actions': [{'type': 'set-iam-policy',
                          'add-bindings':
                              [{'members': ['user:mediapills@gmail.com'],
                                'role': 'roles/owner'}]}]},
            session_factory=session_factory)

        client = policy.resource_manager.get_client()
        actual_bindings = client.execute_query('getIamPolicy', get_iam_policy_params)
        expected_bindings = [{'members': ['user:alex.karpitski@gmail.com',
                                          'user:dkhanas@gmail.com',
                                          'user:pavel_mitrafanau@epam.com',
                                          'user:yauhen_shaliou@comelfo.com'],
                              'role': 'roles/owner'}]
        self.assertEqual(actual_bindings['bindings'], expected_bindings)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], resource_full_name)

        if self.recording:
            time.sleep(1)

        actual_bindings = client.execute_query('getIamPolicy', get_iam_policy_params)
        expected_bindings[0]['members'].insert(2, 'user:mediapills@gmail.com')
        self.assertEqual(actual_bindings['bindings'], expected_bindings)


class FolderTest(BaseTest):

    def test_folder_query(self):
        resource_name = 'folders/112838955399'
        parent = 'organizations/926683928810'
        session_factory = self.replay_flight_data('folder-query')

        policy = self.load_policy(
            {'name': 'gcp-folder-dryrun',
             'resource': 'gcp.folder',
             'query':
                 [{'parent': parent}]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(resources[0]['parent'], parent)


class ProjectTest(BaseTest):

    @pytest.mark.skipif(
        sys.platform.startswith('win'), reason='windows file path fun')
    def test_propagate_tags(self):
        factory = self.replay_flight_data('project-propagate-tags')

        label_path = os.path.join(
            os.path.dirname(__file__), 'data', 'folder-labels.json')

        p = self.load_policy({
            'name': 'p-label',
            'resource': 'gcp.project',
            'query': [
                {'filter': 'parent.id:389734459213 parent.type:folder'}],
            'filters': [
                {'tag:cost-center': 'absent'}],
            'actions': [
                {'type': 'propagate-labels',
                 'folder-labels': {
                     'url': 'file://%s' % label_path}}
            ],
        }, session_factory=factory)
        resources = p.run()
        assert len(resources) == 3
        # verify we successfully filtered out non active projects
        assert {r['lifecycleState'] for r in resources} == {'ACTIVE', 'DELETE_REQUESTED'}
        # verify tags
        client = p.resource_manager.get_client()
        project = client.execute_query(
            'get', {'projectId': 'c7n-test-target'})
        assert project['labels'] == {'app': 'c7n',
                                     'cost-center': 'qa',
                                     'env_type': 'dev',
                                     'owner': 'testing'}

    def test_project_hierarchy(self):
        factory = self.replay_flight_data('project-hierarchy')
        p = self.load_policy({
            'name': 'p-parents',
            'resource': 'gcp.project',
            'query': [
                {'filter': 'parent.id:389734459213 parent.type:folder'}],
        }, session_factory=factory)
        resources = p.run()
        hierarchy = HierarchyAction({}, p.resource_manager)
        hierarchy.load_hierarchy(resources)
        assert hierarchy.folder_ids == set(('389734459213', '264112811077'))
        hierarchy.load_folders()
        assert hierarchy.folders == {
            '264112811077': {'createTime': '2020-11-05T15:31:46.060Z',
                             'displayName': 'apps',
                             'lifecycleState': 'ACTIVE',
                             'name': 'folders/264112811077',
                             'parent': 'organizations/11144'},
            '389734459213': {'createTime': '2020-11-05T15:32:49.681Z',
                             'displayName': 'ftests',
                             'lifecycleState': 'ACTIVE',
                             'name': 'folders/389734459213',
                             'parent': 'folders/264112811077'}}
        self.assertRaises(NotImplementedError, hierarchy.load_metadata)
        self.assertRaises(NotImplementedError, hierarchy.diff, [])

    def test_project_hierarchy_no_op(self):

        class Sub(HierarchyAction):
            # dummy impl for coverage check
            def load_hierarchy(self, resources):
                pass

            def diff(self, resources):
                return ()

            def load_metadata(self):
                pass

        factory = self.replay_flight_data('project-hierarchy')
        p = self.load_policy({
            'name': 'p-parents',
            'resource': 'gcp.project'}, session_factory=factory)
        hierarchy = Sub({}, p.resource_manager)
        hierarchy.process([])

    def test_project_delete(self):
        factory = self.replay_flight_data('project-delete')
        p = self.load_policy({
            'name': 'p-delete',
            'resource': 'gcp.project',
            'query': [
                {'filter': 'id:hautomation'}],
            'filters': [{
                'lifecycleState': 'ACTIVE'}],
            'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['projectId'] == 'hautomation'
        client = p.resource_manager.get_client()
        project = client.execute_query(
            'get', {'projectId': 'hautomation'})
        assert project['lifecycleState'] != 'ACTIVE'

    def test_project_label(self):
        factory = self.replay_flight_data('project-set-labels')
        p = self.load_policy({
            'name': 'p-set-labels',
            'resource': 'gcp.project',
            'query': [
                {'filter': 'id:c7n-test-target'}],
            'filters': [
                {'tag:app': 'absent'}],
            'actions': [{
                'type': 'set-labels',
                'labels': {
                    'env_type': 'dev',
                    'app': 'c7n'}
            }]}, session_factory=factory)
        resources = p.run()
        assert len(resources) == 1
        client = p.resource_manager.get_client()
        project = client.execute_query(
            'get', {'projectId': 'c7n-test-target'})
        assert project['labels'] == {'app': 'c7n', 'env_type': 'dev'}

    def test_project_set_iam_policy(self):
        resource_full_name = 'cloud-custodian'
        get_iam_policy_params = {'resource': resource_full_name, 'body': {}}
        session_factory = self.replay_flight_data(
            'project-set-iam-policy')

        policy = self.load_policy(
            {'name': 'gcp-project-set-iam-policy',
             'resource': 'gcp.project',
             'filters': [{'type': 'value',
                          'key': 'name',
                          'value': resource_full_name}],
             'actions': [{'type': 'set-iam-policy',
                          'add-bindings':
                              [{'members': ['user:mediapills@gmail.com'],
                                'role': 'roles/automl.admin'}]}]},
            session_factory=session_factory)

        client = policy.resource_manager.get_client()
        actual_bindings = client.execute_query('getIamPolicy', get_iam_policy_params)
        expected_bindings = [{'members': ['user:alex.karpitski@gmail.com'],
                              'role': 'roles/automl.admin'},
                             {'members': ['user:alex.karpitski@gmail.com'],
                              'role': 'roles/billing.projectManager'},
                             {'members': ['user:alex.karpitski@gmail.com'],
                              'role': 'roles/owner'}]
        self.assertEqual(actual_bindings['bindings'], expected_bindings)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], resource_full_name)

        if self.recording:
            time.sleep(1)

        actual_bindings = client.execute_query('getIamPolicy', get_iam_policy_params)
        expected_bindings[0]['members'].append('user:mediapills@gmail.com')
        self.assertEqual(actual_bindings['bindings'], expected_bindings)
