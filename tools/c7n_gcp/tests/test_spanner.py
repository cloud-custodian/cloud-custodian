# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data
import time

from pytest_terraform import terraform


class SpannerInstanceTest(BaseTest):

    def test_spanner_instance_query(self):
        session_factory = self.replay_flight_data('spanner-instance-query')

        policy = {
            'name': 'all-spanner-instances',
            'resource': 'gcp.spanner-instance'
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['displayName'], 'test-instance')
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                "gcp:spanner::cloud-custodian:instance/test-instance",
            ],
        )

    def test_spanner_instance_get(self):
        session_factory = self.replay_flight_data('spanner-instance-get')
        policy = self.load_policy(
            {'name': 'one-spanner-instance',
             'resource': 'gcp.spanner-instance',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('spanner-instance-get.json')
        instances = exec_mode.run(event, None)

        self.assertEqual(instances[0]['state'], 'READY')
        self.assertEqual(instances[0]['config'],
                         'projects/cloud-custodian/instanceConfigs/regional-asia-east1')
        self.assertEqual(instances[0]['name'],
                         'projects/cloud-custodian/instances/custodian-spanner-1')
        self.assertEqual(
            policy.resource_manager.get_urns(instances),
            [
                "gcp:spanner::cloud-custodian:instance/custodian-spanner-1",
            ],
        )

    def test_spanner_instance_delete(self):
        project_id = 'cloud-custodian'
        deleting_instance_name = 'spanner-instance-0'
        non_deleting_instance_name = 'spanner-instance-1'
        session_factory = self.replay_flight_data('spanner-instance-delete',
                                                  project_id=project_id)
        base_policy = {'name': 'spanner-instance-delete',
                       'resource': 'gcp.spanner-instance'}
        policy = self.load_policy(
            dict(base_policy,
                 filters=[{'displayName': deleting_instance_name}],
                 actions=[{'type': 'delete'}]
                 ),
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['displayName'], deleting_instance_name)

        if self.recording:
            time.sleep(10)

        client = policy.resource_manager.get_client()
        result = client.execute_query(
            'list', {'parent': 'projects/' + project_id})
        instances = result['instances']
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['displayName'], non_deleting_instance_name)

    def test_spanner_instance_patch_node_count(self):
        project_id = 'cloud-custodian'
        patching_instance_name = 'spanner-instance-0'
        non_patching_instance_name = 'spanner-instance-1'

        session_factory = self.replay_flight_data('spanner-instance-patch',
                                                  project_id=project_id)
        base_policy = {'name': 'spanner-instance-patch',
                       'resource': 'gcp.spanner-instance'}
        policy = self.load_policy(
            dict(base_policy,
                 filters=[{'type': 'value',
                           'key': 'nodeCount',
                           'value': 1,
                           'op': 'greater-than'}],
                 actions=[{'type': 'set',
                           'nodeCount': 1}]
                 ),
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['displayName'], patching_instance_name)

        if self.recording:
            time.sleep(5)

        client = policy.resource_manager.get_client()
        result = client.execute_query(
            'list', {'parent': 'projects/' + project_id})
        instances = result['instances']

        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0]['displayName'], patching_instance_name)
        self.assertEqual(instances[1]['displayName'], non_patching_instance_name)
        self.assertEqual(instances[0]['nodeCount'], 1)
        self.assertEqual(instances[1]['nodeCount'], 1)

    def test_spanner_instance_set_iam_policy_add(self):
        """
        The case combines all 3 possible ways for the members to form within a single role:
        - the members specified in a policy already exist in a resource;
        - there are existing members in addition to the ones specified in the policy;
        - a new role is added.
        """
        project_id = 'cloud-custodian'
        resource_name = 'spanner-instance-0'
        resource_full_name = 'projects/%s/instances/%s' % (project_id, resource_name)
        session_factory = self.replay_flight_data(
            'spanner-instance-set-iam-policy-add', project_id=project_id)
        policy = self.load_policy(
            {'name': 'spanner-instance-set-iam-policy-add',
             'resource': 'gcp.spanner-instance',
             'actions': [{'type': 'set-iam-policy',
                          'add-bindings':
                              [{'members': ['user:yauhen_shaliou@comelfo.com'],
                                'role': 'roles/owner'},
                               {'members': ['user:alex.karpitski@gmail.com'],
                                'role': 'roles/viewer'},
                               {'members': ['user:mediapills@gmail.com'],
                                'role': 'roles/editor'}
                               ]}]},
            session_factory=session_factory)

        client = policy.resource_manager.get_client()
        actual_bindings = client.execute_query('getIamPolicy', {'resource': resource_full_name})
        self.assertEqual(actual_bindings['bindings'],
                         [{'members': ['user:yauhen_shaliou@comelfo.com'],
                           'role': 'roles/owner'},
                          {'members': ['user:dkhanas@gmail.com'],
                           'role': 'roles/viewer'}])

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], resource_full_name)

        if self.recording:
            time.sleep(1)

        actual_bindings = client.execute_query('getIamPolicy', {'resource': resource_full_name})
        self.assertEqual(actual_bindings['bindings'],
                         [{'members': ['user:mediapills@gmail.com'],
                           'role': 'roles/editor'},
                          {'members': ['user:yauhen_shaliou@comelfo.com'],
                           'role': 'roles/owner'},
                          {'members': ['user:alex.karpitski@gmail.com',
                                       'user:dkhanas@gmail.com'],
                           'role': 'roles/viewer'}])

    def test_spanner_instance_set_iam_policy_remove(self):
        """
        The case combines all 3 possible ways for the members to form within a single role:
        - no existing members are filtered out by a policy;
        - a part of the existing members is filtered out by the policy;
        - a role is removed completely.
        """
        project_id = 'cloud-custodian'
        resource_name = 'spanner-instance-0'
        resource_full_name = 'projects/%s/instances/%s' % (project_id, resource_name)
        session_factory = self.replay_flight_data('spanner-instance-set-iam-policy-remove',
                                                  project_id=project_id)
        policy = self.load_policy(
            {'name': 'spanner-instance-set-iam-policy-remove',
             'resource': 'gcp.spanner-instance',
             'actions': [{'type': 'set-iam-policy',
                          'remove-bindings':
                              [{'members': ['user:alex.karpitski@gmail.com',
                                            'user:pavel_mitrafanau@epam.com'],
                                'role': 'roles/viewer'},
                               {'members': ['user:mediapills@gmail.com'],
                                'role': 'roles/editor'
                                }]}]},
            session_factory=session_factory)

        client = policy.resource_manager.get_client()
        actual_bindings = client.execute_query('getIamPolicy', {'resource': resource_full_name})
        self.assertEqual(actual_bindings['bindings'],
                         [{'members': ['user:mediapills@gmail.com'],
                           'role': 'roles/editor'},
                          {'members': ['user:yauhen_shaliou@comelfo.com'],
                           'role': 'roles/owner'},
                          {'members': ['user:alex.karpitski@gmail.com',
                                       'user:dkhanas@gmail.com'],
                           'role': 'roles/viewer'}])

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], resource_full_name)

        if self.recording:
            time.sleep(1)

        actual_bindings = client.execute_query('getIamPolicy', {'resource': resource_full_name})
        self.assertEqual(actual_bindings['bindings'],
                         [{'members': ['user:yauhen_shaliou@comelfo.com'],
                           'role': 'roles/owner'},
                          {'members': ['user:dkhanas@gmail.com'],
                           'role': 'roles/viewer'}])

    def test_spanner_instance_filter_iam_query(self):
        project_id = 'gcp-lab-custodian'
        factory = self.replay_flight_data('spanner-instance-filter-iam', project_id=project_id)
        p = self.load_policy({
            'name': 'spanner-instance-filter-iam',
            'resource': 'gcp.spanner-instance',
            'filters': [{
                'type': 'iam-policy',
                'doc': {
                    'key': "bindings[?(role=='roles\\editor' || role=='roles\\owner')]",
                    'op': 'ne',
                    'value': []
                }
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('projects/cloud-custodian/instances/spanner-instance-2',
                         resources[0]['name'])


class SpannerDatabaseInstanceTest(BaseTest):

    def test_spanner_database_instance_query(self):
        session_factory = self.replay_flight_data('spanner-database-instance-query')

        policy = self.load_policy(
            {'name': 'all-spanner-database-instances',
             'resource': 'gcp.spanner-database-instance'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['c7n:spanner-instance']['displayName'], 'custodian-spanner')
        self.assertEqual(resources[0]['c7n:spanner-instance']['state'], 'READY')
        self.assertEqual(resources[0]['c7n:spanner-instance']['nodeCount'], 1)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                "gcp:spanner::cloud-custodian:database/custodian-spanner/custodian-database",
                "gcp:spanner::cloud-custodian:database/custodian-spanner/custodian-favorite-database",  # noqa: E501
            ],
        )

    def test_spanner_database_instance_get(self):
        session_factory = self.replay_flight_data('spanner-database-instance-get')
        policy = self.load_policy(
            {'name': 'one-spanner-database-instance',
             'resource': 'gcp.spanner-database-instance',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('spanner-database-instance-get.json')

        instances = exec_mode.run(event, None)

        self.assertEqual(instances[0]['state'], 'READY')
        self.assertEqual(instances[0]['c7n:spanner-instance']['displayName'], 'custodian-spanner-1')
        self.assertEqual(instances[0]['c7n:spanner-instance']['name'],
                         'projects/cloud-custodian/instances/custodian-spanner-1')
        self.assertEqual(
            policy.resource_manager.get_urns(instances),
            [
                "gcp:spanner::cloud-custodian:database/custodian-spanner-1/db-1",
            ],
        )

    def test_spanner_database_instance_delete(self):
        session_factory = self.replay_flight_data('spanner-database-instance-delete')
        base_policy = {'name': 'gcp-spanner-databases-instance-delete',
                       'resource': 'gcp.spanner-database-instance'}
        policy = self.load_policy(
            dict(base_policy,
                 filters=[{'type': 'value',
                           'key': 'name',
                           'op': 'contains',
                           'value': 'dev'}],
                 actions=[{'type': 'delete'}]
                 ),
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(2, len(resources))
        self.assertEqual(resources[0]['name'].rsplit('/', 1)[-1], 'custodian-database-dev-0')
        self.assertEqual(resources[1]['name'].rsplit('/', 1)[-1], 'custodian-database-dev-1')

        if self.recording:
            time.sleep(5)

        policy = self.load_policy(base_policy, session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(2, len(resources))
        self.assertEqual(resources[0]['name'].rsplit('/', 1)[-1], 'custodian-database-prod')
        self.assertEqual(resources[1]['name'].rsplit('/', 1)[-1], 'custodian-database-qa')

    def test_spanner_database_instance_set_iam_policy(self):
        """
        Among the two possible cases of getting no IAM policies in a resource, the one tested there
        involves filtering everything out with mentioning all the members in a policy.
        """
        project_id = 'cloud-custodian'
        instance_name = 'spanner-instance-0'
        resource_name = 'custodian-database-0'
        resource_full_name = 'projects/%s/instances/%s/databases/%s' % (
            project_id, instance_name, resource_name)
        session_factory = self.replay_flight_data(
            'spanner-database-instance-set-iam-policy-remove-all', project_id=project_id)
        policy = self.load_policy(
            {'name': 'spanner-database-instance-set-iam-policy-remove-all',
             'resource': 'gcp.spanner-database-instance',
             'actions': [{'type': 'set-iam-policy',
                          'remove-bindings': [{'role': 'roles/owner',
                                        'members': ['user:yauhen_shaliou@comelfo.com']},
                                       {'role': 'roles/viewer',
                                        'members': ['user:dkhanas@gmail.com']}]}]},
            session_factory=session_factory)

        client = policy.resource_manager.get_client()
        actual_bindings = client.execute_query('getIamPolicy', {'resource': resource_full_name})
        self.assertEqual(actual_bindings['bindings'],
                         [{'role': 'roles/owner',
                           'members': ['user:yauhen_shaliou@comelfo.com']},
                          {'role': 'roles/viewer',
                           'members': ['user:dkhanas@gmail.com']}])

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], resource_full_name)

        if self.recording:
            time.sleep(1)

        actual_bindings = client.execute_query('getIamPolicy', {'resource': resource_full_name})
        self.assertFalse('bindings' in actual_bindings)

    def test_set_iam_policy_remove_bindings_star(self):
        policy = self.load_policy(
            {'name': 'spanner-database-instance-set-iam-policy-remove-with-star',
             'resource': 'gcp.spanner-database-instance',
             'actions': [{'type': 'set-iam-policy'}]})
        test_method = policy.resource_manager.actions[0]._remove_bindings

        existing_bindings = [{'role': 'roles/owner',
                              'members': ['user:yauhen_shaliou@comelfo.com']},
                             {'role': 'roles/viewer',
                              'members': ['user:dkhanas@gmail.com']}]
        bindings_to_remove = [{'role': 'roles/owner',
                               'members': '*'}]
        expected_bindings = [{'role': 'roles/viewer',
                              'members': ['user:dkhanas@gmail.com']}]

        self.assertEqual(test_method(existing_bindings, bindings_to_remove), expected_bindings)


class TestSpannerInstanceBackup(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        session_factory = self.replay_flight_data('test-spanner-instance-backup',
                                                  project_id=project_id)
        policy = self.load_policy(
            {'name': 'spanner-instance-backup',
             'resource': 'gcp.spanner-backup',
             'filters': [{
                 'type': 'time-range',
                 'value': 29
             }]},
            session_factory=session_factory)

        resources = policy.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'],
                         'projects/cloud-custodian/instances/spanner-instance-0/backups/backup-1')

    def test_spanner_instance_backup_filter_iam_query(self):
        factory = self.replay_flight_data(
            'spanner-instance-backup-filter-iam', project_id='cloud-custodian')
        p = self.load_policy({
            'name': 'spanner-instance-backup-filter-iam',
            'resource': 'gcp.spanner-backup',
            'filters': [{
                'type': 'iam-policy',
                'doc': {
                    'key': "bindings[?(role=='roles/editor' || role=='roles/owner')]",
                    'op': 'ne',
                    'value': []
                }
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(1, len(resources))


@terraform('spanner_backup')
def test_spanner_backup_iam(test):
    session_factory = test.replay_flight_data('spanner-backup-iam')
    policy = test.load_policy({
        'name': 'spanner-backup-iam',
        'resource': 'gcp.spanner-backup',
        'filters': [{
            'type': 'iam-policy',
            'doc': {
                'key': 'bindings[*].role',
                'op': 'intersect',
                'value': ['roles/editor', 'roles/owner']
            }
        }]
    }, session_factory=session_factory)

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['c7n:iamPolicy']['bindings'][0]['role'] == 'roles/editor'
