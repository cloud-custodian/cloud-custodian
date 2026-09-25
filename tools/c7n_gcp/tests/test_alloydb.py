# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from gcp_common import BaseTest


class AlloyDBClusterTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('gcp-alloydb-cluster-query')
        p = self.load_policy({
            'name': 'gcp-alloydb-cluster',
            'resource': 'gcp.alloydb-cluster'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['name'],
            'projects/cloud-custodian/locations/us-central1/'
            'clusters/test-cluster')
        self.assertEqual(resources[0]['state'], 'READY')
        self.assertEqual(resources[0]['labels'], {'env': 'test'})

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            ['gcp:alloydb:us-central1:cloud-custodian:cluster/test-cluster'])


class AlloyDBInstanceTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('gcp-alloydb-instance-query')
        p = self.load_policy({
            'name': 'gcp-alloydb-instance',
            'resource': 'gcp.alloydb-instance'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['name'],
            'projects/cloud-custodian/locations/us-central1/'
            'clusters/test-cluster/instances/test-instance')
        self.assertEqual(resources[0]['instanceType'], 'PRIMARY')

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            ['gcp:alloydb:us-central1:cloud-custodian:'
             'instance/test-instance'])
