# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_gcp.resources.certificatemanager import CertificateManagerCertificate
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
