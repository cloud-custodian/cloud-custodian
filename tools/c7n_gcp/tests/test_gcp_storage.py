# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import time

import pytest
from c7n.exceptions import PolicyValidationError
from c7n_gcp.actions import MethodAction
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


@terraform("bucket_public_access_enforced")
def test_bucket_public_access_enforced(test, bucket_public_access_enforced):
    bucket_name = (
        bucket_public_access_enforced.resources['google_storage_bucket']['bucket']['name'])
    factory = test.replay_flight_data('bucket-public-access-enforced')
    policy = test.load_policy(
        {'name': 'bucket-public-access-enforced',
         'resource': 'gcp.bucket',
         'filters': [
             {'name': bucket_name},
             {'type': 'value',
              'key': 'iamConfiguration.publicAccessPrevention',
              'value': 'enforced',
              'op': 'ne'}],
         'actions': [{'type': 'set-public-access-prevention', 'state': 'enforced'}]},
        session_factory=factory)
    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['name'] == bucket_name

    bucket = policy.resource_manager.get_resource({'bucket_name': bucket_name})
    assert bucket['iamConfiguration']['publicAccessPrevention'] == 'enforced'
    # patching public access prevention must not reset uniform access
    assert bucket['iamConfiguration']['uniformBucketLevelAccess']['enabled'] is True


@terraform("bucket_public_access_inherited")
def test_bucket_public_access_inherited(test, bucket_public_access_inherited):
    bucket_name = (
        bucket_public_access_inherited.resources['google_storage_bucket']['bucket']['name'])
    factory = test.replay_flight_data('bucket-public-access-inherited')
    policy = test.load_policy(
        {'name': 'bucket-public-access-inherited',
         'resource': 'gcp.bucket',
         'filters': [
             {'name': bucket_name},
             {'iamConfiguration.publicAccessPrevention': 'enforced'}],
         'actions': [{'type': 'set-public-access-prevention', 'state': 'inherited'}]},
        session_factory=factory)
    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['name'] == bucket_name

    bucket = policy.resource_manager.get_resource({'bucket_name': bucket_name})
    assert bucket['iamConfiguration']['publicAccessPrevention'] == 'inherited'
    # patching public access prevention must not reset uniform access
    assert bucket['iamConfiguration']['uniformBucketLevelAccess']['enabled'] is True


@pytest.mark.parametrize('rule', [
    pytest.param(
        {'action': {'type': 'SetStorageClass'}, 'condition': {'age': 30}},
        id='storage-class-missing'),
    pytest.param(
        {'action': {'type': 'Delete', 'storageClass': 'NEARLINE'}, 'condition': {'age': 30}},
        id='storage-class-not-allowed'),
    pytest.param(
        {'action': {'type': 'AbortIncompleteMultipartUpload'}, 'condition': {'isLive': True}},
        id='abort-upload-condition'),
    pytest.param(
        {'action': {'type': 'Delete'}, 'condition': {'createdBefore': datetime.date(2020, 1, 1)}},
        id='unquoted-yaml-date'),
    pytest.param(
        {'action': {'type': 'Delete'}, 'condition': {'createdBefore': 'January 1st'}},
        id='date-wrong-format'),
    pytest.param(
        {'action': {'type': 'Delete'}, 'condition': {'sizeAboveBytes': 1048576}},
        id='int64-as-number'),
    pytest.param(
        {'action': {'type': 'Delete'}, 'condition': {'agee': 90}},
        id='misspelled-condition'),
])
def test_bucket_set_lifecycle_rule_invalid(test, rule):
    with pytest.raises(PolicyValidationError):
        test.load_policy(
            {'name': 'bucket-set-lifecycle-rule-invalid',
             'resource': 'gcp.bucket',
             'actions': [{'type': 'set-lifecycle-rule', 'rule': rule}]},
            validate=True)


@terraform("bucket_set_lifecycle_rule")
def test_bucket_set_lifecycle_rule(test, bucket_set_lifecycle_rule):
    delete_at_90 = {'action': {'type': 'Delete'}, 'condition': {'age': 90}}
    delete_at_120 = {'action': {'type': 'Delete'}, 'condition': {'age': 120}}
    delete_old_versions = {
        'action': {'type': 'Delete'}, 'condition': {'daysSinceNoncurrentTime': 7}}
    move_logs_to_nearline = {
        'action': {'type': 'SetStorageClass', 'storageClass': 'NEARLINE'},
        'condition': {'age': 30, 'matchesPrefix': ['logs/']}}
    buckets = bucket_set_lifecycle_rule.resources['google_storage_bucket']
    no_rules = buckets['no_rules']['name']
    other_rules = buckets['other_rules']['name']
    same_rule = buckets['same_rule']['name']

    # replay can't check what was sent, so record the params of each real call
    sent = []
    invoke_api = MethodAction.invoke_api

    def record(action, client, op_name, params):
        sent.append(params)
        return invoke_api(action, client, op_name, params)

    test.patch(MethodAction, 'invoke_api', record)

    factory = test.replay_flight_data('bucket-set-lifecycle-rule')
    policy = test.load_policy(
        {'name': 'bucket-set-lifecycle-rule',
         'resource': 'gcp.bucket',
         'filters': [{'type': 'value', 'key': 'name', 'op': 'in',
                      'value': [no_rules, other_rules, same_rule]}],
         'actions': [
             {'type': 'set-lifecycle-rule', 'rule': delete_at_90},
             {'type': 'set-lifecycle-rule', 'rule': delete_old_versions}]},
        session_factory=factory)
    resources = policy.run()

    existing = [delete_at_120, move_logs_to_nearline]
    before = {r['name']: r.get('lifecycle', {}).get('rule') for r in resources}
    assert before == {no_rules: None, other_rules: existing, same_rule: [delete_at_90]}

    def patch(bucket, metageneration, rules):
        return {'bucket': bucket,
                'ifMetagenerationMatch': metageneration,
                'fields': 'lifecycle',
                'projection': 'noAcl',
                'body': {'lifecycle': {'rule': rules}}}

    # the first action skips same_rule; the second keeps the first action's rule
    assert sent == [
        patch(no_rules, '1', [delete_at_90]),
        patch(other_rules, '1', existing + [delete_at_90]),
        patch(no_rules, '2', [delete_at_90, delete_old_versions]),
        patch(other_rules, '2', existing + [delete_at_90, delete_old_versions]),
        patch(same_rule, '1', [delete_at_90, delete_old_versions]),
    ]

    def rules(name):
        bucket = policy.resource_manager.get_resource({'bucket_name': name})
        return bucket['lifecycle']['rule']

    assert rules(no_rules) == [delete_at_90, delete_old_versions]
    assert rules(other_rules) == existing + [delete_at_90, delete_old_versions]
    assert rules(same_rule) == [delete_at_90, delete_old_versions]


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
        project_id = self.project_id
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
                f"gcp:storage::{project_id}:bucket/staging.cloud-custodian.appspot.com",
            ],
        )

    def test_bucket_get(self):
        project_id = self.project_id
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
                f"gcp:storage::{project_id}:bucket/staging.cloud-custodian.appspot.com",
            ],
        )

    def test_enable_uniform_bucket_level_access(self):
        project_id = self.project_id
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
        project_id = self.project_id
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
