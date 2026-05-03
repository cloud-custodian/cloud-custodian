# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data
from pytest_terraform import terraform


class DnsManagedZoneTest(BaseTest):

    def test_managed_zone_query(self):
        project_id = 'cloud-custodian'
        managed_zone_name = 'custodian'
        session_factory = self.replay_flight_data(
            'dns-managed-zone-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-dns-managed-zone-dryrun',
             'resource': 'gcp.dns-managed-zone'},
            session_factory=session_factory)

        managed_zone_resources = policy.run()
        self.assertEqual(managed_zone_resources[0]['name'], managed_zone_name)
        self.assertEqual(
            policy.resource_manager.get_urns(managed_zone_resources),
            [
                'gcp:dns::cloud-custodian:managed-zone/custodian'
            ],
        )

    def test_managed_zone_get(self):
        project_id = 'cloud-custodian'
        resource_name = 'custodian'
        session_factory = self.replay_flight_data(
            'dns-managed-zone-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-dns-managed-zone-dryrun',
             'resource': 'gcp.dns-managed-zone',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['dns.managedZones.create']
             }}, session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('dns-managed-zone-create.json')
        resources = exec_mode.run(event, None)

        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:dns::cloud-custodian:managed-zone/custodian'
            ],
        )

    def test_managed_zone_delete(self):
        project_id = "cloud-custodian"
        resource_name = "custodian-delete-test"

        factory = self.replay_flight_data('dns-managed-zone-delete')
        p = self.load_policy(
            {'name': 'gcp-dns-managed-zone-delete',
             'resource': 'gcp.dns-managed-zone',
             'filters': [{'name': resource_name}],
             'actions': ['delete']},
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = p.resource_manager.get_client()
        result = client.execute_query('list', {"project": project_id})
        self.assertNotIn(resource_name, result['managedZones'])


class DnsPolicyTest(BaseTest):

    def test_policy_query(self):
        project_id = 'cloud-custodian'
        policy_name = 'custodian'
        session_factory = self.replay_flight_data(
            'dns-policy-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-dns-policy-dryrun',
             'resource': 'gcp.dns-policy'},
            session_factory=session_factory)

        policy_resources = policy.run()
        self.assertEqual(policy_resources[0]['name'], policy_name)
        self.assertEqual(
            policy.resource_manager.get_urns(policy_resources),
            [
                'gcp:dns::cloud-custodian:policy/custodian'
            ],
        )

    def test_policy_get(self):
        project_id = 'cloud-custodian'
        policy_name = 'custodian'
        session_factory = self.replay_flight_data(
            'dns-policy-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-dns-policy-dryrun',
             'resource': 'gcp.dns-policy',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['dns.policies.create']
             }}, session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('dns-policy-create.json')
        resources = exec_mode.run(event, None)

        self.assertEqual(resources[0]['name'], policy_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:dns::cloud-custodian:policy/custodian'
            ],
        )


class TestDnsResourceRecordsFilter(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        session_factory = self.replay_flight_data(
            'test-dns-resource-records-filter-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'dns-resource-record',
             'resource': 'gcp.dns-managed-zone',
             'filters': [{'type': 'records-sets',
                          'attrs': [{
                              'type': 'value',
                              'key': 'type',
                              'op': 'eq',
                              'value': 'TXT'
                          }]
            }]},
            session_factory=session_factory)

        policy_resources = policy.run()

        self.assertEqual(len(policy_resources), 1)
        self.assertEqual(policy_resources[0]['name'], 'zone-277-red')


@terraform('dns_managed_zone_set_labels')
def test_managed_zone_set_labels(test, dns_managed_zone_set_labels):
    project_id = dns_managed_zone_set_labels['google_dns_managed_zone.default.project']
    zone_name = dns_managed_zone_set_labels['google_dns_managed_zone.default.name']

    factory = test.replay_flight_data('dns-managed-zone-set-label')
    policy = test.load_policy(
        {
            'name': 'gcp-dns-managed-zone-set-label',
            'resource': 'gcp.dns-managed-zone',
            'filters': [{'name': zone_name}],
            'actions': [{'type': 'set-labels', 'labels': {'env': 'not-the-default'}}]
        },
        session_factory=factory
    )

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['labels']['env'] == 'default'

    client = policy.resource_manager.get_client()
    result = client.execute_query('get', {'project': project_id, 'managedZone': zone_name})
    assert result['labels']['env'] == 'not-the-default'
