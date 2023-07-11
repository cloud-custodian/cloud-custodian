# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


def test_data_proc_query(test):
    test.set_regions('us-central1')
    project_id = 'cloud-custodian'
    factory = test.replay_flight_data('test_dataproc_clusters_query', project_id=project_id)
    p = test.load_policy(
        {'name': 'dataproc_clusters', 'resource': 'gcp.dataproc-clusters'},
        session_factory=factory
    )
    resources = p.run()

    assert len(resources) ==  1
    assert resources[0]['clusterName'] == 'cluster-test'
    assert p.resource_manager.get_urns(resources) == [
        'gcp:dataproc:us-central1:cloud-custodian:dataproc/cluster-test'
    ]

    test.check_report_fields(p, resources)
