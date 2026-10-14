# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform


@terraform("bucket_iam_policy_matched")
def test_bucket_set_iam_policy_matched_glob_admin(test, bucket_iam_policy_matched):
    """
    iam-policy filter with glob + value_type: normalize
    on the role, glob on the member, then remove-bindings: matched.

    Bucket has a SA in four roles:
      - roles/storage.objectAdmin  -> matches roles/*admin (normalized to objectadmin)
      - roles/storage.admin        -> matches roles/*admin directly
      - roles/storage.legacyBucketOwner -> does NOT match roles/*admin
      - roles/storage.objectViewer -> does NOT match roles/*admin

    Also has allAuthenticatedUsers in roles/storage.objectAdmin to verify that
    non-SA members in a matching role are left untouched.

    Policy:
      filters:
        - type: iam-policy
          user-role:
            role: {op: glob, value_type: normalize, value: 'roles/*admin'}
            user: {op: glob, value: 'serviceAccount:*'}
      actions:
        - type: set-iam-policy
          remove-bindings: matched
    """
    bucket_name = bucket_iam_policy_matched.resources['google_storage_bucket']['bucket']['name']
    sa_email = (
        'serviceAccount:'
        + bucket_iam_policy_matched.resources['google_service_account']['sa']['email']
    )
    factory = test.replay_flight_data('bucket-iam-policy-matched-glob-admin')

    policy = test.load_policy(
        {
            'name': 'bucket-iam-policy-matched-glob-admin',
            'resource': 'gcp.bucket',
            'filters': [
                {'type': 'value', 'key': 'name', 'value': bucket_name},
                {
                    'type': 'iam-policy',
                    'user-role': {
                        'role': {
                            'op': 'glob',
                            'value_type': 'normalize',
                            'value': 'roles/*admin',
                        },
                        'user': {'op': 'glob', 'value': 'serviceAccount:*'},
                    },
                },
            ],
            'actions': [{'type': 'set-iam-policy', 'remove-bindings': 'matched'}],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1

    client = policy.resource_manager.get_client()
    updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
    bindings = {b['role']: b['members'] for b in updated_policy.get('bindings', [])}

    assert sa_email not in bindings.get('roles/storage.objectAdmin', [])
    assert sa_email not in bindings.get('roles/storage.admin', [])

    assert 'allAuthenticatedUsers' in bindings.get('roles/storage.objectAdmin', [])

    assert sa_email in bindings.get('roles/storage.legacyBucketOwner', [])
    assert sa_email in bindings.get('roles/storage.objectViewer', [])


@terraform("bucket_iam_policy_matched")
def test_bucket_set_iam_policy_matched_exact_role(test, bucket_iam_policy_matched):
    """
    Exact role matching using op: in — equivalent to targeting roles/owner and
    roles/editor at the project level.

    Only the SA binding for roles/storage.legacyBucketOwner is removed; all
    other bindings are untouched.
    """
    bucket_name = bucket_iam_policy_matched.resources['google_storage_bucket']['bucket']['name']
    sa_email = (
        'serviceAccount:'
        + bucket_iam_policy_matched.resources['google_service_account']['sa']['email']
    )
    factory = test.replay_flight_data('bucket-iam-policy-matched-exact-role')

    policy = test.load_policy(
        {
            'name': 'bucket-iam-policy-matched-exact-role',
            'resource': 'gcp.bucket',
            'filters': [
                {'type': 'value', 'key': 'name', 'value': bucket_name},
                {
                    'type': 'iam-policy',
                    'user-role': {
                        'role': {
                            'op': 'in',
                            'value': ['roles/storage.legacyBucketOwner'],
                        },
                        'user': {'op': 'glob', 'value': 'serviceAccount:*'},
                    },
                },
            ],
            'actions': [{'type': 'set-iam-policy', 'remove-bindings': 'matched'}],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1

    client = policy.resource_manager.get_client()
    updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
    bindings = {b['role']: b['members'] for b in updated_policy.get('bindings', [])}

    assert sa_email not in bindings.get('roles/storage.legacyBucketOwner', [])

    assert sa_email in bindings.get('roles/storage.objectAdmin', [])
    assert sa_email in bindings.get('roles/storage.admin', [])
    assert sa_email in bindings.get('roles/storage.objectViewer', [])


@terraform("bucket_iam_policy_matched")
def test_bucket_set_iam_policy_matched_chained_exact_and_glob(test, bucket_iam_policy_matched):
    """
    chained iam-policy filters combine exact-role matching
    (op: in) AND glob-pattern matching (op: glob + normalize)
    into a single policy via accumulated c7n:matched-iam-bindings.

    After running, only roles/storage.objectViewer retains the SA.
    """
    bucket_name = bucket_iam_policy_matched.resources['google_storage_bucket']['bucket']['name']
    sa_email = (
        'serviceAccount:'
        + bucket_iam_policy_matched.resources['google_service_account']['sa']['email']
    )
    factory = test.replay_flight_data('bucket-iam-policy-matched-chained')

    policy = test.load_policy(
        {
            'name': 'bucket-iam-policy-matched-chained',
            'resource': 'gcp.bucket',
            'filters': [
                {'type': 'value', 'key': 'name', 'value': bucket_name},
                {
                    'type': 'iam-policy',
                    'user-role': {
                        'role': {
                            'op': 'in',
                            'value': ['roles/storage.legacyBucketOwner'],
                        },
                        'user': {'op': 'glob', 'value': 'serviceAccount:*'},
                    },
                },
                {
                    'type': 'iam-policy',
                    'user-role': {
                        'role': {
                            'op': 'glob',
                            'value_type': 'normalize',
                            'value': 'roles/*admin',
                        },
                        'user': {'op': 'glob', 'value': 'serviceAccount:*'},
                    },
                },
            ],
            'actions': [{'type': 'set-iam-policy', 'remove-bindings': 'matched'}],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1

    matched = resources[0]['c7n:matched-iam-bindings']
    matched_roles = {pair['role'] for pair in matched}
    assert 'roles/storage.legacyBucketOwner' in matched_roles
    assert 'roles/storage.objectAdmin' in matched_roles
    assert 'roles/storage.admin' in matched_roles

    client = policy.resource_manager.get_client()
    updated_policy = client.execute_query('getIamPolicy', {'bucket': bucket_name})
    bindings = {b['role']: b['members'] for b in updated_policy.get('bindings', [])}

    assert sa_email not in bindings.get('roles/storage.objectAdmin', [])
    assert sa_email not in bindings.get('roles/storage.admin', [])
    assert sa_email not in bindings.get('roles/storage.legacyBucketOwner', [])

    assert sa_email in bindings.get('roles/storage.objectViewer', [])

    assert 'allAuthenticatedUsers' in bindings.get('roles/storage.objectAdmin', [])
