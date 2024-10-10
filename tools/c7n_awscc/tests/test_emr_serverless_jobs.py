from .common import BaseTest


class TestEMRServerlessJobs(BaseTest):

    def test_emr_serverless_jobs(self):
        factory = self.replay_flight_data('test_emr_serverless_jobs')
        p = self.load_policy({
            'name': 'emr-serverless-jobs',
            'resource': 'emr-serverless-jobs',
        }, session_factory=factory)
        resources = p.run()
        self.assertTrue(len(resources) > 0)

