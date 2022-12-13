# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data


class DataflowJobTest(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('dataflow-job', project_id)
        p = self.load_policy({
            'name': 'dataflow-job',
            'resource': 'gcp.dataflow-job'},
            session_factory=factory)
        resource = p.run()
        self.assertEqual(len(resource), 1)
        self.assertEqual(resource[0]['name'], 'test')
        self.assertEqual(resource[0]['projectId'], project_id)
        self.assertEqual(resource[0]['location'], 'us-central1')
        self.assertTrue(resource[0].get("environment"))
        self.assertEqual(
            p.resource_manager.get_urns(resource),
            [
                'gcp:dataflow:us-central1:cloud-custodian:job/test'
            ],
        )

    def test_job_get(self):
        project_id = 'cloud-custodian'
        jod_id = "2019-05-16_04_24_18-6110555549864901093"
        factory = self.replay_flight_data(
            'dataflow-get-resource', project_id)
        p = self.load_policy({'name': 'job',
                              'resource': 'gcp.dataflow-job',
                              'mode': {
                                  'type': 'gcp-audit',
                                  'methods': ['storage.buckets.update']}
                              },
                             session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('df-job-create.json')
        resource = exec_mode.run(event, None)
        self.assertEqual(resource[0]['id'], jod_id)
        self.assertEqual(resource[0]['name'], 'test1')
        self.assertEqual(resource[0]['projectId'], project_id)
        self.assertEqual(resource[0]['location'], 'us-central1')
        self.assertEqual(
            p.resource_manager.get_urns(resource),
            [
                'gcp:dataflow:us-central1:cloud-custodian:job/test1'
            ],
        )
