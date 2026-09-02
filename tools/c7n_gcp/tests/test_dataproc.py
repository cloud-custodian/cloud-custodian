# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data


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


def test_data_proc_cluster_get_resource(test):
    project_id = test.project_id
    test.set_regions('us-central1')
    factory = test.replay_flight_data(
        'test_dataproc_clusters_query',
        project_id=project_id,
    )
    p = test.load_policy(
        {'name': 'dataproc_clusters', 'resource': 'gcp.dataproc-clusters'},
        session_factory=factory,
    )

    resource = p.resource_manager.get_resource({
        'resourceName': (
            'projects/cloud-custodian/regions/us-central1/clusters/cluster-test'
        ),
    })

    assert resource['clusterName'] == 'cluster-test'
    assert 'lifecycleConfig' not in resource['config']
    assert resource['c7n:region']['name'] == 'us-central1'


def test_data_proc_cluster_audit_events(test):
    project_id = test.project_id
    test.set_regions('us-central1')
    factory = test.replay_flight_data(
        'test_dataproc_clusters_query',
        project_id=project_id,
    )
    p = test.load_policy(
        {
            'name': 'dataproc-cluster-audit',
            'resource': 'gcp.dataproc-clusters',
            'mode': {
                'type': 'gcp-audit',
                'methods': [
                    'google.cloud.dataproc.v1.ClusterController.CreateCluster',
                    'google.cloud.dataproc.v1.ClusterController.UpdateCluster',
                ],
            },
            'filters': [
                {
                    'type': 'value',
                    'key': 'config.lifecycleConfig.idleDeleteTtl',
                    'value': 'absent',
                },
            ],
        },
        session_factory=factory,
    )
    exec_mode = p.get_execution_mode()

    for event_name in (
        'dataproc-cluster-create.json',
        'dataproc-cluster-update.json',
    ):
        resources = exec_mode.run(event_data(event_name), None)

        assert len(resources) == 1
        assert resources[0]['clusterName'] == 'cluster-test'
        assert resources[0]['c7n:region']['name'] == 'us-central1'
