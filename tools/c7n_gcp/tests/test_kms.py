# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data


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
