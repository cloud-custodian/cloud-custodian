# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class TestDataprocCluster(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('test_dataproc_clusters_query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'dataproc_clusters',
             'resource': 'gcp.dataproc-clusters'},
            session_factory=factory)

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['clusterName'], 'cluster-test')
