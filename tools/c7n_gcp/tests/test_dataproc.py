# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class DataprocTest(BaseTest):

    def test_dataproc_clusters_filter_iam_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data(
            'dataproc-clusters-filter-iam',
            project_id=project_id,
        )

        p = self.load_policy({
            'name': 'dataproc-filter-iam',
            'resource': 'gcp.dataproc-clusters',
            'filters': [{
                'type': 'iam-policy',
                'doc': {'key': 'bindings[*].members[]',
                        'op': 'intersect',
                        'value': ['user:yauhen_shaliou@epam.com']}
            }]
        }, session_factory=factory, config={'region': 'us-central1'})
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('cluster-8065', resources[0]['clusterName'])


def test_data_proc_query(test):
    test.set_regions('us-central1')
    project_id = 'cloud-custodian'
    factory = test.replay_flight_data('test_dataproc_clusters_query', project_id=project_id)
    p = test.load_policy(
        {'name': 'dataproc_clusters', 'resource': 'gcp.dataproc-clusters'},
        session_factory=factory
    )
    resources = p.run()

    assert len(resources) == 1
    assert resources[0]['clusterName'] == 'cluster-test'
    assert p.resource_manager.get_urns(resources) == [
        'gcp:dataproc:us-central1:cloud-custodian:dataproc/cluster-test'
    ]

    test.check_report_fields(p, resources)
