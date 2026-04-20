# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data
from googleapiclient.errors import HttpError
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


@terraform("dns_enable_dnssec")
def test_dns_managed_zone_enable_dnssec(test, dns_enable_dnssec):
    zone_name = dns_enable_dnssec.resources['google_dns_managed_zone']['public_zone']['name']
    project_id = dns_enable_dnssec.resources['google_dns_managed_zone']['public_zone']['project']

    factory = test.replay_flight_data('dns-managed-zone-enable-dnssec')
    p = test.load_policy(
        {
            'name': 'gcp-dns-enable-dnssec',
            'resource': 'gcp.dns-managed-zone',
            'filters': [
                {'type': 'value', 'key': 'visibility', 'op': 'eq', 'value': 'public'},
                {'type': 'value', 'key': 'dnssecConfig.state', 'op': 'ne', 'value': 'on'},
            ],
            'actions': [{'type': 'enable-dnssec'}],
        },
        session_factory=factory,
    )
    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['name'] == zone_name
    assert resources[0]['dnssecConfig']['state'] == 'off'

    client = p.resource_manager.get_client()
    result = client.execute_query('get', {'project': project_id, 'managedZone': zone_name})
    assert result['dnssecConfig']['state'] == 'on'


@terraform("dns_set_dnssec_key_specs_dnssec_on")
def test_dns_managed_zone_set_dnssec_key_specs_handle_immutable_field_error(
    test, dns_set_dnssec_key_specs_dnssec_on
):
    zone = dns_set_dnssec_key_specs_dnssec_on.resources['google_dns_managed_zone']['public_zone']
    zone_name = zone['name']
    project_id = zone['project']

    factory = test.replay_flight_data('dns-managed-zone-set-key-specs-immutable')
    p = test.load_policy(
        {
            'name': 'gcp-dns-set-dnssec-key-specs-immutable',
            'resource': 'gcp.dns-managed-zone',
            'filters': [
                # Intentionally omit the state filter so the already-enabled
                # zone is included and the PATCH triggers the immutableField error
                {'type': 'value', 'key': 'visibility', 'op': 'eq', 'value': 'public'},
            ],
            'actions': [
                {
                    'type': 'set-dnssec-key-specs',
                    # Use ecdsap384sha384 so we can confirm below that the zone's
                    # key specs were NOT changed (still rsasha256 from provisioning)
                    'defaultKeySpecs': [
                        {'keyType': 'keySigning', 'algorithm': 'ecdsap384sha384',
                         'keyLength': 384},
                        {'keyType': 'zoneSigning', 'algorithm': 'ecdsap384sha384',
                         'keyLength': 384},
                    ],
                }
            ],
        },
        session_factory=factory,
    )
    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['name'] == zone_name
    assert resources[0]['dnssecConfig']['state'] == 'on'

    client = p.resource_manager.get_client()
    result = client.execute_query('get', {'project': project_id, 'managedZone': zone_name})
    returned_specs = result['dnssecConfig']['defaultKeySpecs']
    assert all(s['algorithm'] != 'ecdsap384sha384' for s in returned_specs)


@terraform("dns_set_dnssec_key_specs")
def test_dns_managed_zone_set_dnssec_key_specs_handle_error_reraises(
    test, dns_set_dnssec_key_specs
):
    factory = test.replay_flight_data('dns-managed-zone-set-key-specs-error')
    p = test.load_policy(
        {
            'name': 'gcp-dns-set-dnssec-key-specs-error',
            'resource': 'gcp.dns-managed-zone',
            'filters': [
                {'type': 'value', 'key': 'visibility', 'op': 'eq', 'value': 'public'},
                {'type': 'value', 'key': 'dnssecConfig.state', 'op': 'ne', 'value': 'on'},
            ],
            'actions': [
                {
                    'type': 'set-dnssec-key-specs',
                    'defaultKeySpecs': [
                        {'keyType': 'keySigning', 'algorithm': 'rsasha256', 'keyLength': 2048},
                        {'keyType': 'keySigning', 'algorithm': 'rsasha256', 'keyLength': 2048},
                    ],
                }
            ],
        },
        session_factory=factory,
    )
    with test.assertRaises(HttpError):
        p.run()


@terraform("dns_set_dnssec_key_specs")
def test_dns_managed_zone_set_dnssec_key_specs(test, dns_set_dnssec_key_specs):
    zone = dns_set_dnssec_key_specs.resources['google_dns_managed_zone']['public_zone']
    zone_name = zone['name']
    project_id = zone['project']
    key_specs = [
        {'keyType': 'keySigning', 'algorithm': 'rsasha256', 'keyLength': 2048},
        {'keyType': 'zoneSigning', 'algorithm': 'rsasha512', 'keyLength': 1024},
    ]

    factory = test.replay_flight_data('dns-managed-zone-set-key-specs')
    p = test.load_policy(
        {
            'name': 'gcp-dns-set-dnssec-key-specs',
            'resource': 'gcp.dns-managed-zone',
            'filters': [
                {'type': 'value', 'key': 'visibility', 'op': 'eq', 'value': 'public'},
                {'type': 'value', 'key': 'dnssecConfig.state', 'op': 'ne', 'value': 'on'},
            ],
            'actions': [
                {
                    'type': 'set-dnssec-key-specs',
                    'defaultKeySpecs': key_specs,
                }
            ],
        },
        session_factory=factory,
    )
    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['name'] == zone_name

    client = p.resource_manager.get_client()
    result = client.execute_query('get', {'project': project_id, 'managedZone': zone_name})
    returned_specs = result['dnssecConfig']['defaultKeySpecs']
    assert len(returned_specs) == 2
    assert returned_specs[0]['keyType'] == 'keySigning'
    assert returned_specs[0]['algorithm'] == 'rsasha256'
    assert returned_specs[1]['keyType'] == 'zoneSigning'
    assert returned_specs[1]['algorithm'] == 'rsasha512'
