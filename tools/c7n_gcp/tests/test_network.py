
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
