from ..azure_common import BaseTest


class StreamJobTest(BaseTest):

    def test_stream_job_resource(self):
        p = self.load_policy(
            {
                "name": "test-stream-job-resource",
                "resource": "azure.stream-job",
            }
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['name'].endswith('218stream_job'))

    def test_schema_validate(self):
        p = self.load_policy({
            'name': 'test-stream-job-resource',
            'resource': 'azure.stream-job'
        }, validate=True)
        self.assertTrue(p)
