# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest
from pytest_terraform import terraform


class DataprocTest(BaseTest):

    def test_dataproc_clusters_filter_iam_query(self):
        project_id = self.project_id
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


@terraform('dataproc_cluster')
def test_dataproc_clusters_get(test, dataproc_cluster):
    project_id = dataproc_cluster['google_dataproc_cluster.default.project']
    region = dataproc_cluster['google_dataproc_cluster.default.region']
    cluster_name = dataproc_cluster['google_dataproc_cluster.default.name']

    factory = test.replay_flight_data('dataproc-clusters-get', project_id=project_id)
    p = test.load_policy({
        'name': 'dataproc-get',
        'resource': 'gcp.dataproc-clusters',
    }, session_factory=factory)
    resource = p.resource_manager.get_resource({
        'resourceName': f'projects/{project_id}/regions/{region}/clusters/{cluster_name}',
    })
    assert resource['clusterName'] == cluster_name
    assert resource['c7n:region']['name'] == region


def test_data_proc_query(test):
    project_id = test.project_id
    test.set_regions('us-central1')
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
