# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from c7n_gcp.resources.network import Interconnect, InterconnectAttachment
from gcp_common import BaseTest, event_data
from googleapiclient.errors import HttpError
from pytest_terraform import terraform


class FirewallTest(BaseTest):

    def test_firewall_get(self):
        project_id = self.project_id
        factory = self.replay_flight_data(
            'firewall-get', project_id=project_id)
        p = self.load_policy({'name': 'fw', 'resource': 'gcp.firewall'},
                             session_factory=factory)
        fw = p.resource_manager.get_resource({
            'resourceName': f'projects/{project_id}/global/firewalls/allow-inbound-xyz',
            'firewall_rule_id': '4746899906201084445',
            'project_id': project_id})
        self.assertEqual(fw['name'], 'allow-inbound-xyz')
        self.assertEqual(
            p.resource_manager.get_urns([fw]),
            [f"gcp:compute::{project_id}:firewall/allow-inbound-xyz"],
        )

    def test_firewall_modify(self):
        project_id = self.project_id
        factory = self.replay_flight_data('firewall-modify', project_id=project_id)
        p = self.load_policy(
            {'name': 'fdelete',
             'resource': 'gcp.firewall',
             'filters': [{'name': 'test'}],
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
        project_id = self.project_id
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


class NetworkTest(BaseTest):

    def test_network_get(self):
        project_id = self.project_id
        factory = self.replay_flight_data(
            'network-get-resource', project_id=project_id)
        p = self.load_policy({'name': 'network', 'resource': 'gcp.vpc'},
                             session_factory=factory)
        network = p.resource_manager.get_resource({
            "resourceName":
                f"//compute.googleapis.com/projects/{project_id}/"
                "global/networks/default"})
        self.assertEqual(network['name'], 'default')
        self.assertEqual(network['autoCreateSubnetworks'], True)
        self.assertEqual(
            p.resource_manager.get_urns([network]),
            [
                f'gcp:compute::{project_id}:vpc/default',
            ],
        )


class SubnetTest(BaseTest):

    def test_subnet_get(self):
        project_id = self.project_id
        factory = self.replay_flight_data(
            'subnet-get-resource', project_id=project_id)
        p = self.load_policy({'name': 'subnet', 'resource': 'gcp.subnet'},
                             session_factory=factory)
        subnet = p.resource_manager.get_resource({
            "resourceName":
                f"//compute.googleapis.com/projects/{project_id}/"
                "regions/us-central1/subnetworks/default",
            "project_id": project_id,
            "subnetwork_name": "default"})
        self.assertEqual(subnet['name'], 'default')
        self.assertEqual(subnet['privateIpGoogleAccess'], True)

        self.assertEqual(
            p.resource_manager.get_urns([subnet]),
            [f"gcp:compute:us-central1:{project_id}:subnet/default"],
        )

    def test_subnet_set_flow(self):
        project_id = self.project_id
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
        project_id = self.project_id
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
        project_id = self.project_id
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
            [f"gcp:compute:us-central1:{project_id}:router/test-router"],
        )

    def test_router_get(self):
        project_id = self.project_id
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
            [f"gcp:compute:us-central1:{project_id}:router/test-router-2"],
        )

    def test_router_delete(self):
        project_id = self.project_id
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
        project_id = self.project_id
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
            [f"gcp:compute::{project_id}:route/default-route-f414047c633f96ab"],
        )

    def test_route_get(self):
        project_id = self.project_id
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
            [f"gcp:compute::{project_id}:route/test-route-2"],
        )


class TestVPCFirewallFilter(BaseTest):

    def test_vpc_firewall_filter_query(self):
        project_id = self.project_id
        factory = self.replay_flight_data(
            'test_vpc_firewall_filter_query', project_id=project_id)
        p = self.load_policy(
            {'name': 'vpc-firewall',
             'resource': 'gcp.vpc',
             'filters': [{
                 'type': 'firewall',
                 'attrs': [{
                     'type': 'value',
                     'key': 'id',
                     'op': 'eq',
                     'value': '2383043984399442858'
                 }]
             }]}, validate=True, session_factory=factory)

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#network')


def test_interconnect_labels(test):
    # Provisioning real interconnect resources requires a physical connection, so minimal
    # mock responses have been written manually to the recording directory.
    factory = test.replay_flight_data("interconnect-labels")

    policy = test.load_policy(
        {
            "name": "interconnect-labels",
            "resource": "gcp.interconnect",
            "filters": [{"name": "my-interconnect"}],
            "actions": [{"type": "set-labels", "labels": {"env": "not-the-default"}}],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]["labels"]["env"] == "default"

    client = policy.resource_manager.get_client()
    resource = Interconnect.resource_type.refresh(client, resources[0])
    assert resource["labels"]["env"] == "not-the-default"
    assert resource["labelFingerprint"] != resources[0]["labelFingerprint"]


@terraform('interconnect_attachment_labels')
def test_interconnect_attachment_labels(test, interconnect_attachment_labels):
    attachment = interconnect_attachment_labels.resources[
        'google_compute_interconnect_attachment']['c7n_test_attachment']
    project_id = attachment['project']
    name = attachment['name']
    label_fingerprint = attachment['label_fingerprint']
    labels = attachment['labels']

    # Confirm start label
    assert labels['env'] == 'default'

    # Update the label
    factory = test.replay_flight_data(
        'interconnect-attachment-set-labels', project_id=project_id)
    policy = test.load_policy(
        {
            'name': 'interconnect-attachment-set-labels',
            'resource': 'gcp.interconnect-attachment',
            'filters': [{'name': name}],
            'actions': [{'type': 'set-labels', 'labels': {'env': 'not-the-default'}}],
        },
        session_factory=factory,
    )
    resources = policy.run()
    assert len(resources) == 1

    # Refresh the resource, confirm label and fingerprint changed
    client = policy.resource_manager.get_client()
    resource = InterconnectAttachment.resource_type.refresh(client, resources[0])
    assert resource["labels"]["env"] == "not-the-default"
    assert resource["labelFingerprint"] != label_fingerprint
