# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from gcp_common import BaseTest, event_data
from c7n_gcp.resources.network import PortRangeFirewallFilter
from c7n.filters.vpc import ParseMaxAndMinPorts
from googleapiclient.errors import HttpError


class FirewallTest(BaseTest):

    def test_firewall_get(self):
        factory = self.replay_flight_data(
            'firewall-get', project_id='cloud-custodian')
        p = self.load_policy({'name': 'fw', 'resource': 'gcp.firewall'},
                             session_factory=factory)
        fw = p.resource_manager.get_resource({
            'resourceName': 'projects/cloud-custodian/global/firewalls/allow-inbound-xyz',
            'firewall_rule_id': '4746899906201084445',
            'project_id': 'cloud-custodian'})
        self.assertEqual(fw['name'], 'allow-inbound-xyz')
        self.assertEqual(
            p.resource_manager.get_urns([fw]),
            ["gcp:compute::cloud-custodian:firewall/allow-inbound-xyz"],
        )

    def test_firewall_modify(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('firewall-modify', project_id=project_id)
        p = self.load_policy(
            {'name': 'fdelete',
             'resource': 'gcp.firewall',
             'filters': [{
                 'type': 'value',
                 'key': 'name',
                 'value': 'test'
             }],
             'actions': [{'type': 'modify', 'priority': 500, 'targetTags': ['newtag']}]
             },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)
        client = p.resource_manager.get_client()
        result = client.execute_query('get', {'project': project_id, 'firewall': 'test'})
        self.assertEqual(result["targetTags"][0], 'newtag')
        self.assertEqual(result["priority"], 500)

    def test_firewall_delete(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('firewall-delete', project_id=project_id)
        p = self.load_policy(
            {'name': 'fdelete',
             'resource': 'gcp.firewall',
             'filters': [{
                 'type': 'value',
                 'key': 'name',
                 'value': 'test'
             }],
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)
        client = p.resource_manager.get_client()
        try:
            result = client.execute_query(
                'get', {'project': project_id,
                        'firewall': 'test'})
            self.fail('found deleted firewall: %s' % result)
        except HttpError as e:
            self.assertTrue("was not found" in str(e))

    def test_firewall_attached_to_cluster_filter(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data(
            'gcp-firewall-attached-to-cluster-filter', project_id=project_id)
        p = self.load_policy(
            {'name': 'gcp-firewall-attached-to-cluster-filter',
             'resource': 'gcp.firewall',
             'filters': ['attached-to-cluster']},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertTrue(resources[0]['network'].endswith('networks/network-129-green'))


class NetworkTest(BaseTest):

    def test_network_get(self):
        factory = self.replay_flight_data(
            'network-get-resource', project_id='cloud-custodian')
        p = self.load_policy({'name': 'network', 'resource': 'gcp.vpc'},
                             session_factory=factory)
        network = p.resource_manager.get_resource({
            "resourceName":
                "//compute.googleapis.com/projects/cloud-custodian/"
                "global/networks/default"})
        self.assertEqual(network['name'], 'default')
        self.assertEqual(network['autoCreateSubnetworks'], True)
        self.assertEqual(
            p.resource_manager.get_urns([network]),
            [
                'gcp:compute::cloud-custodian:vpc/default',
            ],
        )

    def test_firewall_port_range_filter(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data(
            'firewall-port-range-filter', project_id=project_id)
        p = self.load_policy(
            {'name': 'gcp-firewall',
             'resource': 'gcp.firewall',
             'filters': [{
                 'type': 'value',
                 'key': 'name',
                 'op': 'regex',
                 'value': 'example.*'
             }, {
                 'type': 'port-range',
                 'key': 'allowed[?IPProtocol==\'tcp\'].ports[]',
                 'required-ports': '20, 50-60',
                 'allow-partial': False
             }]}, validate=True, session_factory=factory)

        resources = p.run()

        self.assertEqual(len(resources), 1)

    def test_port_range_firewall_filter_is_port_range_token(self):
        tokens_and_expected_results = {'10-20': True, '15': False}

        for token, expected_result in tokens_and_expected_results.items():
            actual_result = PortRangeFirewallFilter._is_port_range_token(token)

            self.assertEqual(actual_result, expected_result)

    def test_port_range_firewall_filter_parse_port_token(self):
        port_token = '25'
        expected_port = 25

        actual_port = ParseMaxAndMinPorts.parse_port_token(port_token)

        self.assertEqual(actual_port, expected_port)

    def test_port_range_firewall_filter_parse_port_token_as_port_range(self):
        port_token = '25'
        expected_range = (25, 25)

        actual_range = PortRangeFirewallFilter._parse_port_token_as_port_range(port_token)

        self.assertEqual(actual_range, expected_range)

    def test_port_range_firewall_filter_parse_port_range_token(self):
        port_range_token = '35-45'
        expected_port_range = (35, 45)

        actual_port_range = ParseMaxAndMinPorts.parse_port_range_token(port_range_token)

        self.assertEqual(actual_port_range, expected_port_range)

    def test_port_range_firewall_filter_parse_ranges(self):
        raw_ranges = '20, 50-51'
        expected_ports = {(20, 20), (50, 51)}

        actual_ports = PortRangeFirewallFilter._parse_ranges(raw_ranges)

        self.assertEqual(actual_ports, expected_ports)

    def test_port_range_firewall_filter_parse_tokens(self):
        raw_tokens = '20, 50-51'
        expected_tokens = ['20', '50-51']

        actual_tokens = PortRangeFirewallFilter._parse_tokens(raw_tokens)

        self.assertEqual(actual_tokens, expected_tokens)

    def test_port_range_firewall_filter_sort_and_merge_intersecting_ranges(self):
        ranges = {(63, 70), (61, 61), (45, 60), (40, 50), (21, 30), (10, 20)}
        expected_ranges = [(10, 30), (40, 61), (63, 70)]

        actual_ranges = PortRangeFirewallFilter._sort_and_merge_intersecting_ranges(ranges)

        self.assertEqual(actual_ranges, expected_ranges)

    def test_port_range_firewall_filter_is_range_intersecting_or_touching_another_range(self):
        ranges_and_expected_results = {
            ((20, 21), (22, 22)): True,
            ((20, 21), (21, 22)): True,
            ((20, 21), (23, 24)): False,
        }

        for ranges, expected_result in ranges_and_expected_results.items():
            range1, range2 = ranges
            actual_result = \
                PortRangeFirewallFilter._is_range_intersecting_or_touching_another_range(
                    range1, range2)
            swap_actual_result = \
                PortRangeFirewallFilter._is_range_intersecting_or_touching_another_range(
                    range2, range1)

            self.assertEqual(actual_result, expected_result)
            self.assertEqual(swap_actual_result, expected_result)

    def test_port_range_firewall_filter_is_subset(self):
        examples = {
            1: (({(10, 20)}, {(10, 10), (11, 25)}), True),
            2: (({(19, 19)}, {(18, 22)}), True),
            3: (({(20, 24)}, {(20, 21), (22, 24)}), True),
            4: (({(20, 24)}, {(20, 21), (23, 24)}), False),
            5: (({(20, 20), (23, 24)}, {(20, 21), (23, 24)}), True),
        }

        for example, containers_and_expected_results in examples.items():
            maybe_subset, container = containers_and_expected_results[0]
            merged_maybe_subset = PortRangeFirewallFilter._sort_and_merge_intersecting_ranges(
                maybe_subset)
            merged_container = PortRangeFirewallFilter._sort_and_merge_intersecting_ranges(
                container)
            actual_result = PortRangeFirewallFilter._is_subset(
                merged_maybe_subset, merged_container)

            self.assertEqual(actual_result, containers_and_expected_results[1])

    def test_route_get_insert(self):
        project_id = 'cloud-custodian'
        network_name = 'https://www.googleapis.com/compute/v1/projects/' \
                       'cloud-custodian/regions/us-east1/subnetworks/subnet'
        factory = self.replay_flight_data('vpc-get-insert', project_id=project_id)

        p = self.load_policy({
            'name': 'gcp-vpc-insert',
            'resource': 'gcp.vpc',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['v1.compute.subnetworks.insert']}},
            session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('gcp-vpc-insert.json')
        subnetworks = exec_mode.run(event, None)

        self.assertEqual(len(subnetworks), 1)
        self.assertEqual(subnetworks[0]['subnetworks'][0], network_name)

    def test_route_get_add_peering(self):
        project_id = 'cloud-custodian'
        network_name = 'https://www.googleapis.com/compute/v1/projects/' \
                       'cloud-custodian/regions/us-east1/subnetworks/subnet'
        factory = self.replay_flight_data('vpc-get-add-peering', project_id=project_id)

        p = self.load_policy({
            'name': 'gcp-vpc-add-peering',
            'resource': 'gcp.vpc',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['v1.compute.subnetworks.addPeering']}},
            session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('gcp-get-add-peering.json')
        subnetworks = exec_mode.run(event, None)

        self.assertEqual(len(subnetworks), 1)
        self.assertEqual(subnetworks[0]['subnetworks'][0], network_name)

    def test_vpc_dns_policy_filter(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('vpc-dns-policy-filter-get', project_id=project_id)

        p = self.load_policy({
            'name': 'vpc-dns-policy',
            'resource': 'gcp.vpc',
            'filters': [{'not': [{
                'type': 'vpc-dns-policy-filter',
                'key': 'enableLogging',
                'op': 'eq',
                'value': True
            }]}]
        },
            session_factory=factory)

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'kseoji')


class SubnetTest(BaseTest):

    def test_subnet_get(self):
        factory = self.replay_flight_data(
            'subnet-get-resource', project_id='cloud-custodian')
        p = self.load_policy({'name': 'subnet', 'resource': 'gcp.subnet'},
                             session_factory=factory)
        subnet = p.resource_manager.get_resource({
            "resourceName":
                "//compute.googleapis.com/projects/cloud-custodian/"
                "regions/us-central1/subnetworks/default",
            "project_id": "cloud-custodian",
            "subnetwork_name": "default"})
        self.assertEqual(subnet['name'], 'default')
        self.assertEqual(subnet['privateIpGoogleAccess'], True)

        self.assertEqual(
            p.resource_manager.get_urns([subnet]),
            ["gcp:compute:us-central1:cloud-custodian:subnet/default"],
        )

    def test_subnet_set_flow(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('subnet-set-flow', project_id=project_id)
        p = self.load_policy({
            'name': 'all-subnets',
            'resource': 'gcp.subnet',
            'filters': [
                {"id": "4686700484947109325"},
                {"enableFlowLogs": "empty"}],
            'actions': ['set-flow-log']}, session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        subnet = resources.pop()
        self.assertEqual(subnet['enableFlowLogs'], False)

        client = p.resource_manager.get_client()
        result = client.execute_query(
            'get', {'project': project_id,
                    'region': 'us-central1',
                    'subnetwork': subnet['name']})
        self.assertEqual(result['enableFlowLogs'], True)

    def test_subnet_set_private_api(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('subnet-set-private-api', project_id=project_id)
        p = self.load_policy({
            'name': 'one-subnet',
            'resource': 'gcp.subnet',
            'filters': [
                {"id": "4686700484947109325"},
                {"privateIpGoogleAccess": False}],
            'actions': ['set-private-api']}, session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        subnet = resources.pop()
        self.assertEqual(subnet['privateIpGoogleAccess'], False)

        client = p.resource_manager.get_client()
        result = client.execute_query(
            'get', {'project': project_id,
                    'region': 'us-central1',
                    'subnetwork': subnet['name']})
        self.assertEqual(result['privateIpGoogleAccess'], True)


class RouterTest(BaseTest):
    def test_router_query(self):
        project_id = 'cloud-custodian'
        session_factory = self.replay_flight_data('router-query', project_id=project_id)

        policy = {
            'name': 'all-routers',
            'resource': 'gcp.router'
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], 'test-router')
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            ["gcp:compute:us-central1:cloud-custodian:router/test-router"],
        )

    def test_router_get(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('router-get', project_id=project_id)

        p = self.load_policy({
            'name': 'router-created',
            'resource': 'gcp.router',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['beta.compute.routers.insert']}},
            session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('router-create.json')
        routers = exec_mode.run(event, None)

        self.assertEqual(len(routers), 1)
        self.assertEqual(routers[0]['bgp']['asn'], 65001)
        self.assertEqual(
            p.resource_manager.get_urns(routers),
            ["gcp:compute:us-central1:cloud-custodian:router/test-router-2"],
        )

    def test_router_delete(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('router-delete', project_id=project_id)

        p = self.load_policy(
            {'name': 'delete-router',
             'resource': 'gcp.router',
             'filters': [{'name': 'test-router'}],
             'actions': ['delete']},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(5)

        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'region': 'us-central1',
                     'filter': 'name = test-router'})

        self.assertEqual(result.get('items', []), [])


class RouteTest(BaseTest):
    def test_route_query(self):
        project_id = 'cloud-custodian'
        session_factory = self.replay_flight_data('route-query', project_id=project_id)

        policy = {
            'name': 'all-routes',
            'resource': 'gcp.route'
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['destRange'], '10.160.0.0/20')
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            ["gcp:compute::cloud-custodian:route/default-route-f414047c633f96ab"],
        )

    def test_route_get(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('route-get', project_id=project_id)

        p = self.load_policy({
            'name': 'route-created',
            'resource': 'gcp.route',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['v1.compute.routes.insert']}},
            session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('route-create.json')
        routes = exec_mode.run(event, None)

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]['destRange'], '10.0.0.0/24')
        self.assertEqual(
            p.resource_manager.get_urns(routes),
            ["gcp:compute::cloud-custodian:route/test-route-2"],
        )
