# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_gcp.resources.certificatemanager import (
    CertificateManagerCertificate,
    CertificateManagerMap,
    CertificateMapEntry
)
from gcp_common import BaseTest


class CertificateManagerTest(BaseTest):

    def test_certificate_query(self):
        """Test certificate manager resource query functionality"""
        session_factory = self.replay_flight_data('certmanager-certificate-query')

        policy = self.load_policy(
            {'name': 'all-certificates',
             'resource': 'gcp.certmanager-certificate'},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['name'].split('/')[-1], 'test-certificate-1')
        self.assertEqual(resources[1]['name'].split('/')[-1], 'test-certificate-2')

        # Test URN generation
        urns = policy.resource_manager.get_urns(resources)
        self.assertTrue(all('certificate' in urn for urn in urns))

    def test_certificate_resource_type_methods(self):
        """Test CertificateManagerCertificate resource type static methods"""
        # Test the static get method
        class MockClient:
            def execute_command(self, op, params):
                return {'name': params['name'], 'status': 'ACTIVE'}

        client = MockClient()
        resource_info = {'name': 'projects/test/locations/global/certificates/test-cert'}
        result = CertificateManagerCertificate.resource_type.get(client, resource_info)

        self.assertEqual(result['name'], resource_info['name'])
        self.assertEqual(result['status'], 'ACTIVE')

        # Test get_label_params method
        resource = {'name': 'projects/test/locations/global/certificates/test-cert'}
        all_labels = {'env': 'prod', 'team': 'backend'}

        params = CertificateManagerCertificate.resource_type.get_label_params(resource, all_labels)

        expected_params = {
            'name': resource['name'],
            'body': {'labels': all_labels},
            'updateMask': 'labels'
        }
        self.assertEqual(params, expected_params)

    def test_certificate_map_query(self):
        """Test certificate map resource query functionality"""
        session_factory = self.replay_flight_data('certmanager-certificate-map-query')

        policy = self.load_policy(
            {'name': 'all-certificate-maps',
             'resource': 'gcp.certmanager-certificate-map'},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(len(resources), 3)
        self.assertEqual(resources[0]['name'].split('/')[-1], 'test-certificate-map-1')
        self.assertEqual(resources[1]['name'].split('/')[-1], 'test-certificate-map-2')
        self.assertEqual(resources[2]['name'].split('/')[-1], 'test-certificate-map-3')

        # Test URN generation
        urns = policy.resource_manager.get_urns(resources)
        self.assertTrue(all('certificate-map' in urn for urn in urns))

    def test_certificate_map_filter_by_labels(self):
        """Test certificate map filtering by labels"""
        session_factory = self.replay_flight_data('certmanager-certificate-map-query')

        policy = self.load_policy(
            {'name': 'test-env-certificate-maps',
             'resource': 'gcp.certmanager-certificate-map',
             'filters': [
                 {'type': 'value',
                  'key': 'labels.environment',
                  'value': 'test'}
             ]},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'].split('/')[-1], 'test-certificate-map-1')
        self.assertEqual(resources[0]['labels']['environment'], 'test')

    def test_certificate_map_filter_by_gclb_targets(self):
        """Test certificate map filtering by GCLB targets"""
        session_factory = self.replay_flight_data('certmanager-certificate-map-query')

        policy = self.load_policy(
            {'name': 'certificate-maps-with-multiple-targets',
             'resource': 'gcp.certmanager-certificate-map',
             'filters': [
                 {'type': 'value',
                  'key': 'length(gclbTargets)',
                  'value': 2,
                  'op': 'gte'}
             ]},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'].split('/')[-1], 'test-certificate-map-2')
        self.assertEqual(len(resources[0]['gclbTargets']), 2)

    def test_certificate_map_resource_type_methods(self):
        """Test CertificateManagerMap resource type static methods"""
        # Test the static get method
        class MockClient:
            def execute_command(self, op, params):
                return {'name': params['name'], 'description': 'Test map'}

        client = MockClient()
        resource_info = {'name': 'projects/test/locations/global/certificateMaps/test-map'}
        result = CertificateManagerMap.resource_type.get(client, resource_info)

        self.assertEqual(result['name'], resource_info['name'])
        self.assertEqual(result['description'], 'Test map')

        # Test get_label_params method
        resource = {'name': 'projects/test/locations/global/certificateMaps/test-map'}
        all_labels = {'env': 'staging', 'team': 'platform'}

        params = CertificateManagerMap.resource_type.get_label_params(resource, all_labels)

        expected_params = {
            'name': resource['name'],
            'body': {'labels': all_labels},
            'updateMask': 'labels'
        }
        self.assertEqual(params, expected_params)

        # Test refresh method
        resource = {'name': 'projects/test/locations/global/certificateMaps/test-map'}
        refreshed = CertificateManagerMap.resource_type.refresh(client, resource)
        self.assertEqual(refreshed['name'], resource['name'])
        self.assertEqual(refreshed['description'], 'Test map')

    def test_certificate_map_delete(self):
        """Test certificate map delete action"""
        resource_name = "custodian-delete-test"

        factory = self.replay_flight_data('certmanager-certificate-map-delete')
        p = self.load_policy(
            {'name': 'gcp-certificate-map-delete',
             'resource': 'gcp.certmanager-certificate-map',
             'filters': [
                 {'type': 'value',
                  'key': 'name',
                  'value': '.*' + resource_name,
                  'op': 'regex'}
             ],
             'actions': ['delete']},
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn(resource_name, resources[0]['name'])

        # Verify the certificate map was deleted by checking the list is empty
        client = p.resource_manager.get_client()
        result = client.execute_query('list', {"parent": "projects/cloud-custodian/locations/-"})
        self.assertEqual(len(result.get('certificateMaps', [])), 0)

    def test_certificate_map_entry_query(self):
        """Test certificate map entry resource query functionality"""
        session_factory = self.replay_flight_data('certmanager-certificate-map-entry-query')

        policy = self.load_policy(
            {'name': 'all-certificate-map-entries',
             'resource': 'gcp.certmanager-certificate-map-entry'},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(len(resources), 4)
        self.assertEqual(resources[0]['name'].split('/')[-1], 'entry-1')
        self.assertEqual(resources[1]['name'].split('/')[-1], 'entry-2')
        self.assertEqual(resources[2]['name'].split('/')[-1], 'wildcard-entry')
        self.assertEqual(resources[3]['name'].split('/')[-1], 'pending-entry')

        # Test URN generation
        urns = policy.resource_manager.get_urns(resources)
        self.assertTrue(all('certificate-map-entry' in urn for urn in urns))

    def test_certificate_map_entry_filter_by_state(self):
        """Test certificate map entry filtering by state"""
        session_factory = self.replay_flight_data('certmanager-certificate-map-entry-query')

        policy = self.load_policy(
            {'name': 'active-certificate-map-entries',
             'resource': 'gcp.certmanager-certificate-map-entry',
             'filters': [
                 {'type': 'value',
                  'key': 'state',
                  'value': 'ACTIVE'}
             ]},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(len(resources), 3)
        self.assertTrue(all(r['state'] == 'ACTIVE' for r in resources))

    def test_certificate_map_entry_filter_by_matcher(self):
        """Test certificate map entry filtering by matcher type"""
        session_factory = self.replay_flight_data('certmanager-certificate-map-entry-query')

        policy = self.load_policy(
            {'name': 'primary-matcher-entries',
             'resource': 'gcp.certmanager-certificate-map-entry',
             'filters': [
                 {'type': 'value',
                  'key': 'matcher',
                  'value': 'PRIMARY'}
             ]},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['matcher'], 'PRIMARY')
        self.assertEqual(resources[0]['name'].split('/')[-1], 'entry-1')

    def test_certificate_map_entry_filter_by_hostname(self):
        """Test certificate map entry filtering by hostname pattern"""
        session_factory = self.replay_flight_data('certmanager-certificate-map-entry-query')

        policy = self.load_policy(
            {'name': 'wildcard-hostname-entries',
             'resource': 'gcp.certmanager-certificate-map-entry',
             'filters': [
                 {'type': 'value',
                  'key': 'hostname',
                  'value': '\\*\\..*',
                  'op': 'regex'}
             ]},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['hostname'], '*.example.org')

    def test_certificate_map_entry_resource_type_methods(self):
        """Test CertificateMapEntry resource type static methods"""
        # Test the static get method
        class MockClient:
            def execute_command(self, op, params):
                return {'name': params['name'], 'state': 'ACTIVE'}

        client = MockClient()
        resource_info = {
            'name': 'projects/test/locations/global/certificateMaps/map1/certificateMapEntries/entry1'
        }
        result = CertificateMapEntry.resource_type.get(client, resource_info)

        self.assertEqual(result['name'], resource_info['name'])
        self.assertEqual(result['state'], 'ACTIVE')

        # Test get_label_params method
        resource = {
            'name': 'projects/test/locations/global/certificateMaps/map1/certificateMapEntries/entry1'
        }
        all_labels = {'env': 'dev', 'owner': 'team-a'}

        params = CertificateMapEntry.resource_type.get_label_params(resource, all_labels)

        expected_params = {
            'name': resource['name'],
            'body': {'labels': all_labels},
            'updateMask': 'labels'
        }
        self.assertEqual(params, expected_params)

        # Test refresh method
        refreshed = CertificateMapEntry.resource_type.refresh(client, resource)
        self.assertEqual(refreshed['name'], resource['name'])
        self.assertEqual(refreshed['state'], 'ACTIVE')
