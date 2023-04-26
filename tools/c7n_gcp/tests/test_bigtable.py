from gcp_common import BaseTest


class BigtableInstanceTest(BaseTest):

    def test_bigtable_instance_cluster_backup_query(self):
        factory = self.replay_flight_data('bigtable-instance-cluster-backup-query')
        p = self.load_policy({
            'name': 'bigtable-instance-cluster-backup',
            'resource': 'gcp.bigtable-instance-cluster-backup',
            'filters': [{
                'type': 'value',
                'key': 'state',
                'value': 'READY'
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/instances'
                                               '/test-260/clusters/test-260-c1/'
                                               'backups/test-backup-258')


class BigtableTimeRangeFilterTest(BaseTest):

    def test_bigtable_time_range_query(self):
        factory = self.replay_flight_data('test-bigtable-time-range-filter')
        p = self.load_policy({
            'name': 'time-range',
            'resource': 'gcp.bigtable-instance-cluster-backup',
            'filters': [{
                'type': 'time-range',
                'value': 30
            }]
        },
            session_factory=factory)
        resources = p.run()

        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/'
                                               'instances/inst258/clusters/'
                                               'inst258-c1/backups/back258')
        self.assertEqual(len(resources), 1)
