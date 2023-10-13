from ..azure_common import BaseTest


class SecurityAssessmentsTest(BaseTest):
    def test_security_assessments_resource(self):
        p = self.load_policy({
            'name': 'test-security-assessments',
            'resource': 'azure.security-assessments',
            'filters': [{
                'type': 'value',
                'key': 'properties.status.code',
                'op': 'eq',
                'value': 'Healthy'}]})
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], '2a548cf9-6de3-491e-b24a-cf277fe36d4d')
