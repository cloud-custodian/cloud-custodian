# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from gcp_common import BaseTest


class BucketTest(BaseTest):

    def test_bucket_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('bucket-query', project_id)
        p = self.load_policy(
            {'name': 'all-buckets',
             'resource': 'gcp.bucket'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], "staging.cloud-custodian.appspot.com")
        self.assertEqual(resources[0]['storageClass'], "STANDARD")

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                "gcp:storage::cloud-custodian:bucket/staging.cloud-custodian.appspot.com",
            ],
        )

    def test_bucket_get(self):
        project_id = 'cloud-custodian'
        bucket_name = "staging.cloud-custodian.appspot.com"
        factory = self.replay_flight_data(
            'bucket-get-resource', project_id)
        p = self.load_policy({'name': 'bucket', 'resource': 'gcp.bucket'},
                             session_factory=factory)
        bucket = p.resource_manager.get_resource({
            "bucket_name": bucket_name,
        })
        self.assertEqual(bucket['name'], bucket_name)
        self.assertEqual(bucket['id'], "staging.cloud-custodian.appspot.com")
        self.assertEqual(bucket['storageClass'], "STANDARD")
        self.assertEqual(bucket['location'], "EU")

        self.assertEqual(
            p.resource_manager.get_urns([bucket]),
            [
                "gcp:storage::cloud-custodian:bucket/staging.cloud-custodian.appspot.com",
            ],
        )

    def test_enable_uniform_bucket_level_access(self):
        project_id = 'custodian-1291'
        bucket_name = 'c7n-dev-test'
        factory = self.replay_flight_data(
            'bucket-uniform-bucket-access', project_id)
        p = self.load_policy({
            'name': 'bucket',
            'resource': 'gcp.bucket',
            'filters': [
                {'name': 'c7n-dev-test'},
                {'iamConfiguration.uniformBucketLevelAccess.enabled': False},
            ],
            'actions': ['set-uniform-access']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)
        bucket = p.resource_manager.get_resource({
            "bucket_name": bucket_name,
        })
        self.assertEqual(bucket['name'], bucket_name)
        self.assertEqual(bucket['id'], bucket_name)
        self.assertEqual(bucket['storageClass'], "REGIONAL")
        self.assertEqual(bucket['location'], "US-EAST1")
        self.assertJmes('iamConfiguration.uniformBucketLevelAccess.enabled', bucket, True)

    def test_bucket_iam_policy_filter(self):
        factory = self.replay_flight_data('bucket-iam-policy')
        p = self.load_policy(
            {'name': 'bucket',
             'resource': 'gcp.bucket',
             'filters': [{
                 'type': 'iam-policy',
                 'doc': {'key': 'bindings[*].members[]',
                 'op': 'intersect',
                 'value': ['allUsers', 'allAuthenticatedUsers']}
             }]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

        for resource in resources:
            self.assertTrue('c7n:iamPolicy' in resource)
            bindings = resource['c7n:iamPolicy']['bindings']
            members = set()
            for binding in bindings:
                for member in binding['members']:
                    members.add(member)
            self.assertTrue('allUsers' in members or 'allAuthenticatedUsers' in members)

    def test_bucket_scc_mode(self):
        project_id = "cloud-custodian"
        bucket_name = "staging.cloud-custodian.appspot.com"
        factory = self.replay_flight_data("bucket-get-resource", project_id)
        p = self.load_policy(
            {"name": "bucket", "resource": "gcp.bucket", "mode": {"type": "gcp-scc", "org": 12345}},
            session_factory=factory,
        )
        [bucket] = p.push(
            # Fake a minimal scc finding for a bucket.
            {"finding": {"resourceName": "//storage.googleapis.com/" + bucket_name}, "resource": {}}
        )

        assert bucket["name"] == bucket_name
        assert bucket["id"] == "staging.cloud-custodian.appspot.com"
        assert bucket["storageClass"] == "STANDARD"
        assert bucket["location"] == "EU"

        assert p.resource_manager.get_urns([bucket]) == [
            "gcp:storage::cloud-custodian:bucket/staging.cloud-custodian.appspot.com",
        ]

    def test_bucket_set_iam_policy_remove_public_access(self):
        project_id = 'cloud-custodian'
        bucket_name = 'cloud-custodian-test-bucket'
        factory = self.replay_flight_data('bucket-set-iam-policy', project_id=project_id)
        policy = self.load_policy(
            {'name': 'bucket-set-iam-policy',
             'resource': 'gcp.bucket',
             'actions': [{
                 'type': 'set-iam-policy',
                 'remove-bindings': [{
                     'members': ['allUsers', 'allAuthenticatedUsers'],
                     'role': 'roles/storage.objectViewer'
                 }]
             }]},
            session_factory=factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], bucket_name)

        client = policy.resource_manager.get_client()
        updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
        all_members = [
            member
            for binding in updated_policy.get('bindings', [])
            for member in binding['members']
        ]
        self.assertNotIn('allUsers', all_members)
        self.assertNotIn('allAuthenticatedUsers', all_members)

    def test_bucket_set_iam_policy_add_bindings(self):
        project_id = 'cloud-custodian'
        bucket_name = 'cloud-custodian-test-bucket'
        factory = self.replay_flight_data(
            'bucket-set-iam-policy-add-bindings', project_id=project_id)
        policy = self.load_policy(
            {'name': 'bucket-set-iam-policy-add-bindings',
             'resource': 'gcp.bucket',
             'actions': [{
                 'type': 'set-iam-policy',
                 'add-bindings': [{
                     'members': ['user:alice@example.com'],
                     'role': 'roles/storage.objectViewer'
                 }]
             }]},
            session_factory=factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], bucket_name)

        client = policy.resource_manager.get_client()
        updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
        viewer_binding = next(
            (b for b in updated_policy.get('bindings', [])
             if b['role'] == 'roles/storage.objectViewer'),
            None
        )
        self.assertIsNotNone(viewer_binding)
        self.assertIn('user:alice@example.com', viewer_binding['members'])

    def test_bucket_set_iam_policy_remove_wildcard(self):
        project_id = 'cloud-custodian'
        bucket_name = 'cloud-custodian-test-bucket'
        factory = self.replay_flight_data(
            'bucket-set-iam-policy-wildcard', project_id=project_id)
        policy = self.load_policy(
            {'name': 'bucket-set-iam-policy-wildcard',
             'resource': 'gcp.bucket',
             'actions': [{
                 'type': 'set-iam-policy',
                 'remove-bindings': [{
                     'members': '*',
                     'role': 'roles/storage.objectAdmin'
                 }]
             }]},
            session_factory=factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = policy.resource_manager.get_client()
        updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
        roles = [b['role'] for b in updated_policy.get('bindings', [])]
        self.assertNotIn('roles/storage.objectAdmin', roles)

    def test_bucket_set_iam_policy_remove_all_authenticated_users(self):
        project_id = 'cloud-custodian'
        bucket_name = 'cloud-custodian-test-bucket'
        factory = self.replay_flight_data(
            'bucket-set-iam-policy-all-authenticated', project_id=project_id)
        policy = self.load_policy(
            {'name': 'bucket-set-iam-policy-all-authenticated',
             'resource': 'gcp.bucket',
             'actions': [{
                 'type': 'set-iam-policy',
                 'remove-bindings': [{
                     'members': ['allAuthenticatedUsers'],
                     'role': 'roles/storage.objectViewer'
                 }]
             }]},
            session_factory=factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = policy.resource_manager.get_client()
        updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
        all_members = [
            member
            for binding in updated_policy.get('bindings', [])
            for member in binding['members']
        ]
        self.assertNotIn('allAuthenticatedUsers', all_members)
        self.assertIn('user:alice@example.com', all_members)

    def test_bucket_set_iam_policy_multiple_roles(self):
        project_id = 'cloud-custodian'
        bucket_name = 'cloud-custodian-test-bucket'
        factory = self.replay_flight_data(
            'bucket-set-iam-policy-multi-role', project_id=project_id)
        policy = self.load_policy(
            {'name': 'bucket-set-iam-policy-multi-role',
             'resource': 'gcp.bucket',
             'actions': [{
                 'type': 'set-iam-policy',
                 'remove-bindings': [
                     {'members': ['allUsers', 'allAuthenticatedUsers'],
                      'role': 'roles/storage.objectViewer'},
                     {'members': ['allUsers', 'allAuthenticatedUsers'],
                      'role': 'roles/storage.objectCreator'},
                 ]
             }]},
            session_factory=factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = policy.resource_manager.get_client()
        updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
        all_members = [
            member
            for binding in updated_policy.get('bindings', [])
            for member in binding['members']
        ]
        self.assertNotIn('allUsers', all_members)
        self.assertNotIn('allAuthenticatedUsers', all_members)
        self.assertIn('user:alice@example.com', all_members)
        roles = [b['role'] for b in updated_policy.get('bindings', [])]
        self.assertNotIn('roles/storage.objectViewer', roles)

    def test_bucket_set_iam_policy_add_and_remove_remove_wins(self):
        project_id = 'cloud-custodian'
        bucket_name = 'cloud-custodian-test-bucket'
        factory = self.replay_flight_data(
            'bucket-set-iam-policy-add-and-remove', project_id=project_id)
        policy = self.load_policy(
            {'name': 'bucket-set-iam-policy-add-and-remove',
             'resource': 'gcp.bucket',
             'actions': [{
                 'type': 'set-iam-policy',
                 'add-bindings': [
                     {'members': ['user:bob@example.com'],
                      'role': 'roles/storage.objectViewer'},
                     {'members': ['user:alice@example.com'],
                      'role': 'roles/storage.objectAdmin'},
                 ],
                 'remove-bindings': [
                     {'members': ['user:alice@example.com'],
                      'role': 'roles/storage.objectAdmin'},
                 ]
             }]},
            session_factory=factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = policy.resource_manager.get_client()
        updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
        bindings_by_role = {
            b['role']: b['members'] for b in updated_policy.get('bindings', [])}
        self.assertIn(
            'user:bob@example.com',
            bindings_by_role.get('roles/storage.objectViewer', []))
        self.assertIn(
            'user:alice@example.com',
            bindings_by_role.get('roles/storage.objectViewer', []))
        self.assertNotIn('roles/storage.objectAdmin', bindings_by_role)

    def test_bucket_set_iam_policy_remove_nonexistent_is_noop(self):
        project_id = 'cloud-custodian'
        bucket_name = 'cloud-custodian-test-bucket'
        factory = self.replay_flight_data(
            'bucket-set-iam-policy-idempotent', project_id=project_id)
        policy = self.load_policy(
            {'name': 'bucket-set-iam-policy-idempotent',
             'resource': 'gcp.bucket',
             'actions': [{
                 'type': 'set-iam-policy',
                 'remove-bindings': [{
                     'members': ['allUsers', 'allAuthenticatedUsers'],
                     'role': 'roles/storage.objectViewer'
                 }]
             }]},
            session_factory=factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = policy.resource_manager.get_client()
        updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
        roles = [b['role'] for b in updated_policy.get('bindings', [])]
        self.assertIn('roles/storage.legacyBucketOwner', roles)
        self.assertNotIn('roles/storage.objectViewer', roles)

    def test_bucket_label(self):
        # Set the "env" label to not the default
        factory = self.replay_flight_data('bucket-label')
        p = self.load_policy(
            {
                'name': 'bucket-label',
                'resource': 'gcp.bucket',
                'filters': [{
                    'type': 'value',
                    'key': 'name',
                    'value': 'c7n-bucket',
                }],
                'actions': [
                    {'type': 'set-labels',
                     'labels': {'env': 'not-the-default'}}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['labels']['env'], 'default')

        # Fetch the dataset manually to confirm the label was changed
        client = p.resource_manager.get_client()
        result = client.execute_query('get', {'bucket': 'c7n-bucket'})
        self.assertEqual(result['labels']['env'], 'not-the-default')
