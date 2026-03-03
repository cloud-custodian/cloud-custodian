# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from gcp_common import BaseTest
from pytest_terraform import terraform


@terraform("bucket_set_iam_policy")
def test_bucket_set_iam_policy_remove_public_access(test, bucket_set_iam_policy):
    bucket_name = bucket_set_iam_policy.resources['google_storage_bucket']['bucket']['name']
    sa_email = (
        "serviceAccount:"
        + bucket_set_iam_policy.resources['google_service_account']['legitimate_member']['email']
    )
    factory = test.replay_flight_data('bucket-set-iam-policy')

    policy = test.load_policy(
        {'name': 'bucket-set-iam-policy',
            'resource': 'gcp.bucket',
            'filters': [{
                'type': 'iam-policy',
                'doc': {
                    'key': 'bindings[*].members[]',
                    'op': 'intersect',
                    'value': ['allUsers', 'allAuthenticatedUsers'],
                }
            }],
            'actions': [{
                'type': 'set-iam-policy',
                'remove-bindings': [
                    {
                        'members': ['allUsers', 'allAuthenticatedUsers'],
                        'role': 'roles/storage.objectViewer'
                    },
                    {
                        'members': ['allUsers', 'allAuthenticatedUsers'],
                        'role': 'roles/storage.legacyBucketReader'
                    },
                ]
            }]},
        session_factory=factory)
    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['name'] == bucket_name

    client = policy.resource_manager.get_client()
    updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
    all_members = [
        member
        for binding in updated_policy.get('bindings', [])
        for member in binding['members']
    ]
    assert 'allUsers' not in all_members
    assert 'allAuthenticatedUsers' not in all_members
    assert sa_email in all_members


@terraform("bucket_set_iam_policy")
def test_bucket_set_iam_policy_add_bindings(test, bucket_set_iam_policy):
    bucket_name = bucket_set_iam_policy.resources['google_storage_bucket']['bucket']['name']
    sa_email = (
        "serviceAccount:"
        + bucket_set_iam_policy.resources['google_service_account']['legitimate_member']['email']
    )
    factory = test.replay_flight_data('bucket-set-iam-policy-add-bindings')
    policy = test.load_policy(
        {'name': 'bucket-set-iam-policy-add-bindings',
         'resource': 'gcp.bucket',
         'filters': [{'type': 'value', 'key': 'name', 'value': bucket_name}],
         'actions': [{
             'type': 'set-iam-policy',
             'add-bindings': [{
                 'members': [sa_email],
                 'role': 'roles/storage.legacyBucketReader'
             }]
         }]},
        session_factory=factory)

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['name'] == bucket_name

    client = policy.resource_manager.get_client()
    updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
    legacy_reader_binding = next(
        (b for b in updated_policy.get('bindings', [])
         if b['role'] == 'roles/storage.legacyBucketReader'),
        None
    )
    assert legacy_reader_binding is not None
    assert sa_email in legacy_reader_binding['members']


@terraform("bucket_set_iam_policy")
def test_bucket_set_iam_policy_remove_wildcard(test, bucket_set_iam_policy):
    bucket_name = bucket_set_iam_policy.resources['google_storage_bucket']['bucket']['name']
    factory = test.replay_flight_data('bucket-set-iam-policy-wildcard')
    policy = test.load_policy(
        {'name': 'bucket-set-iam-policy-wildcard',
         'resource': 'gcp.bucket',
         'filters': [{'type': 'value', 'key': 'name', 'value': bucket_name}],
         'actions': [{
             'type': 'set-iam-policy',
             'remove-bindings': [{
                 'members': '*',
                 'role': 'roles/storage.objectViewer'
             }]
         }]},
        session_factory=factory)

    resources = policy.run()
    assert len(resources) == 1

    client = policy.resource_manager.get_client()
    updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
    roles = [b['role'] for b in updated_policy.get('bindings', [])]
    assert 'roles/storage.objectViewer' not in roles


@terraform("bucket_set_iam_policy")
def test_bucket_set_iam_policy_add_and_remove_remove_wins(test, bucket_set_iam_policy):
    bucket_name = bucket_set_iam_policy.resources['google_storage_bucket']['bucket']['name']
    sa_email = (
        "serviceAccount:"
        + bucket_set_iam_policy.resources['google_service_account']['legitimate_member']['email']
    )
    factory = test.replay_flight_data('bucket-set-iam-policy-add-and-remove')
    policy = test.load_policy(
        {'name': 'bucket-set-iam-policy-add-and-remove',
         'resource': 'gcp.bucket',
         'filters': [{'type': 'value', 'key': 'name', 'value': bucket_name}],
         'actions': [{
             'type': 'set-iam-policy',
             'add-bindings': [
                 {'members': [sa_email], 'role': 'roles/storage.objectAdmin'},
             ],
             'remove-bindings': [
                 {'members': [sa_email], 'role': 'roles/storage.objectAdmin'},
             ]
         }]},
        session_factory=factory)

    resources = policy.run()
    assert len(resources) == 1

    client = policy.resource_manager.get_client()
    updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
    roles = [b['role'] for b in updated_policy.get('bindings', [])]
    assert 'roles/storage.objectAdmin' not in roles


@terraform("bucket_set_iam_policy")
def test_bucket_set_iam_policy_remove_nonexistent_is_noop(test, bucket_set_iam_policy):
    bucket_name = bucket_set_iam_policy.resources['google_storage_bucket']['bucket']['name']
    sa_email = (
        "serviceAccount:"
        + bucket_set_iam_policy.resources['google_service_account']['legitimate_member']['email']
    )
    factory = test.replay_flight_data('bucket-set-iam-policy-idempotent')
    policy = test.load_policy(
        {'name': 'bucket-set-iam-policy-idempotent',
         'resource': 'gcp.bucket',
         'filters': [{'type': 'value', 'key': 'name', 'value': bucket_name}],
         'actions': [{
             'type': 'set-iam-policy',
             'remove-bindings': [{
                 'members': ['allUsers', 'allAuthenticatedUsers'],
                 'role': 'roles/storage.objectAdmin'
             }]
         }]},
        session_factory=factory)

    resources = policy.run()
    assert len(resources) == 1

    client = policy.resource_manager.get_client()
    updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
    roles = [b['role'] for b in updated_policy.get('bindings', [])]
    assert 'roles/storage.objectAdmin' not in roles
    all_members = [
        member
        for binding in updated_policy.get('bindings', [])
        for member in binding['members']
    ]
    assert sa_email in all_members


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
