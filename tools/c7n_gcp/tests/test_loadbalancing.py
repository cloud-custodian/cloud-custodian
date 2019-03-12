# Copyright 2019 Capital One Services, LLC
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


class LoadBalancingAddressTest(BaseTest):

    def test_loadbalancing_address_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-addresses-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-addresses',
             'resource': 'gcp.loadbalancing-address'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#address')
        self.assertEqual(resources[0]['address'], '35.193.10.19')

    def test_loadbalancing_address_get(self):
        factory = self.replay_flight_data('lb-addresses-get')
        p = self.load_policy(
            {'name': 'one-region-address',
             'resource': 'gcp.loadbalancing-address'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'new1',
             'region': 'us-central1'})
        self.assertEqual(instance['kind'], 'compute#address')
        self.assertEqual(instance['address'], '35.193.10.19')


class LoadBalancingUrlMapTest(BaseTest):

    def test_loadbalancing_url_map_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-url-maps-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-url-maps',
             'resource': 'gcp.loadbalancing-url-map'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#urlMap')
        self.assertEqual(resources[0]['fingerprint'], 'GMqHBoGzLDY=')

    def test_loadbalancing_url_map_get(self):
        factory = self.replay_flight_data('lb-url-maps-get')
        p = self.load_policy(
            {'name': 'one-lb-url-map',
             'resource': 'gcp.loadbalancing-url-map'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'lb'})
        self.assertEqual(instance['kind'], 'compute#urlMap')
        self.assertEqual(instance['fingerprint'], 'GMqHBoGzLDY=')


class LoadBalancingTargetTcpProxyTest(BaseTest):

    def test_loadbalancing_target_tcp_proxy_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-target-tcp-proxies-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-target-tcp-proxies',
             'resource': 'gcp.loadbalancing-target-tcp-proxy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#targetTcpProxy')
        self.assertEqual(resources[0]['name'], 'newlb1-target-proxy')

    def test_loadbalancing_target_tcp_proxy_get(self):
        factory = self.replay_flight_data('lb-target-tcp-proxies-get')
        p = self.load_policy(
            {'name': 'one-lb-target-tcp-proxy',
             'resource': 'gcp.loadbalancing-target-tcp-proxy'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'newlb1-target-proxy'})
        self.assertEqual(instance['kind'], 'compute#targetTcpProxy')
        self.assertEqual(instance['name'], 'newlb1-target-proxy')


class LoadBalancingTargetSslProxyTest(BaseTest):

    def test_loadbalancing_target_ssl_proxy_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-target-ssl-proxies-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-target-ssl-proxies',
             'resource': 'gcp.loadbalancing-target-ssl-proxy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#targetSslProxy')
        self.assertEqual(resources[0]['name'], 'lb2-target-proxy')

    def test_loadbalancing_target_ssl_proxy_get(self):
        factory = self.replay_flight_data('lb-target-ssl-proxies-get')
        p = self.load_policy(
            {'name': 'one-lb-target-ssl-proxy',
             'resource': 'gcp.loadbalancing-target-ssl-proxy'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'lb2-target-proxy'})
        self.assertEqual(instance['kind'], 'compute#targetSslProxy')
        self.assertEqual(instance['name'], 'lb2-target-proxy')


class LoadBalancingSslPolicyTest(BaseTest):

    def test_loadbalancing_ssl_policy_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-ssl-policies-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-ssl-policies',
             'resource': 'gcp.loadbalancing-ssl-policy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#sslPolicy')
        self.assertEqual(resources[0]['name'], 'newpolicy')

    def test_loadbalancing_ssl_policy_get(self):
        factory = self.replay_flight_data('lb-ssl-policies-get')
        p = self.load_policy(
            {'name': 'one-lb-ssl-policies',
             'resource': 'gcp.loadbalancing-ssl-policy'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'newpolicy'})
        self.assertEqual(instance['kind'], 'compute#sslPolicy')
        self.assertEqual(instance['name'], 'newpolicy')
