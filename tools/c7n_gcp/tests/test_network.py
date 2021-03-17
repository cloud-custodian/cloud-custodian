# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from gcp_common import BaseTest, event_data
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

    def test_firewall_delete(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('firewall-delete', project_id=project_id)
        p = self.load_policy(
            {'name': 'fdelete',
             'resource': 'gcp.firewall',
             'filters': [{'name': 'test'}],
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
