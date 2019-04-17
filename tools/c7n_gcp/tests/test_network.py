# Copyright 2018-2019 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from gcp_common import BaseTest


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


class SubnetTest(BaseTest):

    def test_subnet_get(self):
        factory = self.replay_flight_data(
            'subnet-get-resource', project_id='cloud-custodian')
        p = self.load_policy({'name': 'subnet', 'resource': 'gcp.subnet'},
                             session_factory=factory)
        subnet = p.resource_manager.get_resource({
            "location": "us-central1",
            "project_id": "cloud-custodian",
            "subnetwork_id": "4686700484947109325",
            "subnetwork_name": "default"})
        self.assertEqual(subnet['name'], 'default')
        self.assertEqual(subnet['privateIpGoogleAccess'], True)

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
        project_id = 'atomic-shine-231410'
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

    def test_router_get(self):
        project_id = 'atomic-shine-231410'
        session_factory = self.replay_flight_data('router-get', project_id=project_id)

        policy = {
            'name': 'one-router',
            'resource': 'gcp.router'
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory)

        router = policy.resource_manager.get_resource(
            {'project_id': project_id,
             'region': 'us-central1',
             'name': 'test-router'})

        self.assertEqual(router['bgp']['asn'], 65000)


class RouteTest(BaseTest):
    def test_route_query(self):
        project_id = 'atomic-shine-231410'
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

    def test_route_get(self):
        project_id = 'atomic-shine-231410'
        session_factory = self.replay_flight_data('route-get', project_id=project_id)

        policy = {
            'name': 'one-route',
            'resource': 'gcp.route'
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory)

        route = policy.resource_manager.get_resource(
            {'project_id': project_id,
             'name': 'default-route-748fda88a0393274'})

        self.assertEqual(route['destRange'], '192.168.0.0/24')
