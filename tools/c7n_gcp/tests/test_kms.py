# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from gcp_common import BaseTest, event_data
from pytest_terraform import terraform


class KmsKeyRingTest(BaseTest):
    def test_kms_keyring_query_unspecified_location(self):
        project_id = 'cloud-custodian'
        location_name = 'us-central1'
        keyring_name = 'cloud-custodian'
        resource_name = 'projects/{}/locations/{}/keyRings/{}'.\
            format(project_id, location_name, keyring_name)
        session_factory = self.replay_flight_data(
            'kms-keyring-query-unspecified_location', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-kms-keyring-dryrun',
             'resource': 'gcp.kms-keyring'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:cloudkms:us-central1:cloud-custodian:keyring/cloud-custodian',
            ],
        )

    def test_kms_keyring_query_array(self):
        project_id = 'cloud-custodian'
        location_name_1 = 'asia-east1'
        location_name_2 = 'us-central1'
        keyring_name_1 = 'cloud-custodian-asia'
        keyring_name_2 = 'cloud-custodian'
        resource_name_1 = 'projects/{}/locations/{}/keyRings/{}'.\
            format(project_id, location_name_1, keyring_name_1)
        resource_name_2 = 'projects/{}/locations/{}/keyRings/{}'. \
            format(project_id, location_name_2, keyring_name_2)
        session_factory = self.replay_flight_data('kms-keyring-query-array', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-kms-keyring-dryrun',
             'resource': 'gcp.kms-keyring',
             'query': [{'location': [location_name_1, location_name_2]}]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name_1)
        self.assertEqual(resources[1]['name'], resource_name_2)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:cloudkms:asia-east1:cloud-custodian:keyring/cloud-custodian-asia',
                'gcp:cloudkms:us-central1:cloud-custodian:keyring/cloud-custodian',
            ],
        )

    def test_kms_keyring_query(self):
        project_id = 'cloud-custodian'
        location_name = 'us-central1'
        keyring_name = 'cloud-custodian'
        resource_name = 'projects/{}/locations/{}/keyRings/{}'.\
            format(project_id, location_name, keyring_name)
        session_factory = self.replay_flight_data('kms-keyring-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-kms-keyring-dryrun',
             'resource': 'gcp.kms-keyring',
             'query': [{'location': location_name}]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:cloudkms:us-central1:cloud-custodian:keyring/cloud-custodian',
            ],
        )

    def test_kms_keyring_get(self):
        project_id = 'cloud-custodian'
        location_name = 'us-central1'
        keyring_name = 'cloud-custodian'
        resource_name = 'projects/{}/locations/{}/keyRings/{}'. \
            format(project_id, location_name, keyring_name)
        session_factory = self.replay_flight_data('kms-keyring-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-kms-keyring-dryrun',
             'resource': 'gcp.kms-keyring',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['CreateKeyRing']
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('kms-keyring-create.json')
        resources = exec_mode.run(event, None)

        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:cloudkms:us-central1:cloud-custodian:keyring/cloud-custodian',
            ],
        )

    def test_kms_keyring_filter_iam_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('kms-keyring-filter-iam', project_id=project_id)
        p = self.load_policy({
            'name': 'kms-keyring-filter-iam',
            'resource': 'gcp.kms-keyring',
            'filters': [{
                'type': 'iam-policy',
                'doc': {'key': 'bindings[*].members[]',
                        'op': 'intersect',
                        'value': ['allUsers', 'allAuthenticatedUsers']}
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual(
            'projects/cloud-custodian/locations/us-central1/keyRings/custodian-test-keyring',
            resources[0]['name'])


class KmsCryptoKeyTest(BaseTest):
    def test_kms_cryptokey_query(self):
        project_id = 'cloud-custodian'
        location_name = 'us-central1'
        keyring_name = 'cloud-custodian'
        cryptokey_name = 'cloud-custodian'
        parent_resource_name = 'projects/{}/locations/{}/keyRings/{}'\
            .format(project_id, location_name, keyring_name)
        resource_name = '{}/cryptoKeys/{}'.format(parent_resource_name, cryptokey_name)
        session_factory = self.replay_flight_data('kms-cryptokey-query', project_id=project_id)

        filter_parent_annotation_key = 'c7n:kms-keyring'
        policy = self.load_policy(
            {'name': 'gcp-kms-cryptokey-dryrun',
             'resource': 'gcp.kms-cryptokey',
             'query': [{'location': location_name}],
             'filters': [{
                 'type': 'value',
                 'key': '\"{}\".name'.format(filter_parent_annotation_key),
                 'op': 'regex',
                 'value': parent_resource_name
             }]},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()
        # If fails there, policies using filters for the resource
        # need to be updated since the key has been changed.
        self.assertEqual(parent_annotation_key, filter_parent_annotation_key)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(resources[0][parent_annotation_key]['name'], parent_resource_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:cloudkms:us-central1:cloud-custodian:cryptokey/cloud-custodian/cloud-custodian',  # noqa: E501
            ],
        )

    def test_kms_cryptokey_get(self):
        project_id = 'cloud-custodian'
        location_name = 'us-central1'
        keyring_name = 'cloud-custodian'
        cryptokey_name = 'cloud-custodian'
        parent_resource_name = 'projects/{}/locations/{}/keyRings/{}' \
            .format(project_id, location_name, keyring_name)
        resource_name = '{}/cryptoKeys/{}'.format(parent_resource_name, cryptokey_name)
        session_factory = self.replay_flight_data('kms-cryptokey-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-kms-cryptokey-dryrun',
             'resource': 'gcp.kms-cryptokey',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['CreateCryptoKey']
             }},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        exec_mode = policy.get_execution_mode()
        event = event_data('kms-cryptokey-create.json')
        resources = exec_mode.run(event, None)

        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(resources[0][parent_annotation_key]['name'], parent_resource_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:cloudkms:us-central1:cloud-custodian:cryptokey/cloud-custodian/cloud-custodian',  # noqa: E501
            ],
        )

    def test_kms_cryptokey_iam_policy_filter(self):
        factory = self.replay_flight_data('kms-cryptokey-iam-policy')
        p = self.load_policy(
            {'name': 'resource',
             'resource': 'gcp.kms-cryptokey',
             'query': [{'location': 'global'}],
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

    def test_kms_cryptokey_label(test):
        # Set the 'env' label to not the default
        factory = test.replay_flight_data('kms-cryptokey-label')
        key_name = (
            'projects/cloud-custodian/locations/us-central1/keyRings/c7n-test-keyring-bunny/cryptoKeys/c7n-test-cryptokey'
        )
        p = test.load_policy(
            {
                'name': 'kms-cryptokey-label',
                'resource': 'gcp.kms-cryptokey',
                'query': [{'location': 'us-central1'}],
                'filters': [{
                    'type': 'value',
                    'key': 'name',
                    'value': key_name,
                }],
                'actions': [
                    {'type': 'set-labels',
                     'labels': {'env': 'production'}}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['labels']['env'], 'default')

        # Fetch the key manually to confirm the label was changed
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'get',
            {'name': key_name}
        )
        test.assertEqual(result['labels']['env'], 'production')


class KmsCryptoKeyVersionTest(BaseTest):
    def test_kms_cryptokey_version_query(self):
        project_id = 'cloud-custodian'
        location_name = 'us-central1'
        keyring_name = 'cloud-custodian'
        cryptokey_name = 'cloud-custodian'
        cryptokey_version_name = '1'
        parent_resource_name = 'projects/{}/locations/{}/keyRings/{}/cryptoKeys/{}' \
            .format(project_id, location_name, keyring_name, cryptokey_name)
        resource_name = '{}/cryptoKeyVersions/{}'.format(
            parent_resource_name, cryptokey_version_name)
        session_factory = self.replay_flight_data(
            'kms-cryptokey-version-query', project_id=project_id)

        filter_parent_annotation_key = 'c7n:kms-cryptokey'
        policy = self.load_policy(
            {'name': 'gcp-kms-cryptokey-version-dryrun',
             'resource': 'gcp.kms-cryptokey-version',
             'query': [{'location': location_name}],
             'filters': [{
                 'type': 'value',
                 'key': '\"{}\".name'.format(filter_parent_annotation_key),
                 'op': 'regex',
                 'value': parent_resource_name
             }]},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()
        # If fails there, policies using filters for the resource
        # need to be updated since the key has been changed.
        self.assertEqual(parent_annotation_key, filter_parent_annotation_key)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(resources[0][parent_annotation_key]['name'], parent_resource_name)

        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:cloudkms:us-central1:cloud-custodian:cryptokey-version/cloud-custodian/cloud-custodian/1',  # noqa: E501
            ],
        )

    def test_kms_cryptokey_version_get(self):
        project_id = 'cloud-custodian'
        location_name = 'us-central1'
        keyring_name = 'cloud-custodian'
        cryptokey_name = 'cloud-custodian'
        cryptokey_version_name = '1'
        parent_resource_name = 'projects/{}/locations/{}/keyRings/{}/cryptoKeys/{}' \
            .format(project_id, location_name, keyring_name, cryptokey_name)
        resource_name = '{}/cryptoKeyVersions/{}'.format(
            parent_resource_name, cryptokey_version_name)
        session_factory = self.replay_flight_data(
            'kms-cryptokey-version-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-kms-cryptokey-version-dryrun',
             'resource': 'gcp.kms-cryptokey-version',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['CreateCryptoKeyVersion']
             }},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        exec_mode = policy.get_execution_mode()
        event = event_data('kms-cryptokey-version-create.json')
        resources = exec_mode.run(event, None)

        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(resources[0][parent_annotation_key]['name'], parent_resource_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:cloudkms:us-central1:cloud-custodian:cryptokey-version/cloud-custodian/cloud-custodian/1',  # noqa: E501
            ],
        )


@terraform('kms_location')
def test_kms_keyring_filter(test, kms_location):
    session_factory = test.replay_flight_data('kms-keyring-filter')
    policy = test.load_policy({
        'name': 'kms-location',
        'resource': 'gcp.kms-location',
        'filters': [{
            'name':
                f'projects/{kms_location["google_kms_key_ring.c7n.project"]}/locations/us-central1'},
            {
            'not': [{
                    'type': 'keyring',
                    'exist': True}]}]
    }, session_factory=session_factory)

    resources = policy.run()
    assert len(resources) == 0

    policy = test.load_policy({
        'name': 'kms-location',
        'resource': 'gcp.kms-location',
        'filters': [{
            'name':
                f'projects/{kms_location["google_kms_key_ring.c7n.project"]}/locations/us-west1'},
            {
            'not': [{
                    'type': 'keyring',
                    'exist': True}]}]
    }, session_factory=session_factory)

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['name'] == 'projects/cloud-custodian/locations/us-west1'
