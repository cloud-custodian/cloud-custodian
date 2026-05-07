from gcp_common import BaseTest
from c7n.testing import C7N_FUNCTIONAL
from c7n_gcp.client import get_default_project
from pytest_terraform import terraform


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

    def test_bigtable_instance_label(self):
        # Set the "env" label to not the default
        factory = self.replay_flight_data('bigtable-instance-label')
        p = self.load_policy(
            {
                'name': 'bigtable-instance-labels',
                'resource': 'gcp.bigtable-instance',
                'filters': [{
                    'type': 'value',
                    'key': 'name',
                    'op': 'contains',
                    'value': 'c7n-bigtable-instance',
                }],
                'actions': [
                    {'type': 'set-labels',
                     'labels': {'env': 'not-the-default'}}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['labels']['env'], 'default')

        # Fetch the instance manually to confirm the label was changed
        client = p.resource_manager.get_client()
        result = client.execute_query('get', {'name': resources[0]['name']})
        self.assertEqual(result['labels']['env'], 'not-the-default')


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


class BigTableInstanceTableTest(BaseTest):

    def test_bigtable_instance_table_filter_iam_query(self):
        factory = self.replay_flight_data('bigtable-instance-table-filter-iam')
        p = self.load_policy({
            'name': 'bigtable-instance-table-filter-iam',
            'resource': 'gcp.bigtable-instance-table',
            'filters': [{
                'type': 'iam-policy',
                'doc': {
                    'key': 'bindings[?(role==\'roles/owner\' || role==\'roles/editor\')]',
                    'op': 'ne',
                    'value': []
                }
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual('projects/cloud-custodian/instances/custodian-test-instance/tables/custodian-table-red',
                         resources[0]['name'])

    def test_bigtable_instance_table_filter_iam_service_account_query(self):
        factory = self.replay_flight_data('bigtable-instance-table-filter-service-account-iam')
        p = self.load_policy({
            'name': 'bigtable-instance-table-filter-service-account-iam',
            'resource': 'gcp.bigtable-instance-table',
            'filters': [{
                'type': 'iam-policy',
                'doc': {
                    'key': 'bindings[*].members[?contains(@, \'serviceAccount.*\')]',
                    'op': 'ne',
                    'value': []}
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 2)
        self.assertEqual('projects/cloud-custodian/instances/custodian-test-instance/tables/custodian-table-green',
                         resources[0]['name'])
        self.assertEqual('projects/cloud-custodian/instances/custodian-test-instance/tables/custodian-table-red',
                         resources[1]['name'])


@terraform("bigtable_gc_rule")
def test_bigtable_instance_table_filter_gc_rule(test, bigtable_gc_rule):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            'bigtable-instance-table-filter-gc-rule',
            project_id=project_id,
        )
    else:
        session_factory = test.replay_flight_data(
            'bigtable-instance-table-filter-gc-rule',
            project_id=project_id,
        )

    policy = test.load_policy(
        {
            'name': 'bigtable-instance-table-filter-gc-rule',
            'resource': 'gcp.bigtable-instance-table',
            'filters': [{
                'type': 'gc-rule',
                'key': 'columnFamilies.cf_with_gc.gcRule.maxAge',
                'value': '86400s',
                'op': 'eq',
            }]
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['name'].endswith('/tables/c7n-gc-table')
