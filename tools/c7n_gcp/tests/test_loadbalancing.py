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


class LoadBalancingSslCertificateTest(BaseTest):

    def test_loadbalancing_ssl_certificate_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-ssl-certificates-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-ssl-certificates',
             'resource': 'gcp.loadbalancing-ssl-certificate'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#sslCertificate')
        self.assertEqual(resources[0]['name'], 'testcert')

    def test_loadbalancing_ssl_certificate_get(self):
        factory = self.replay_flight_data('lb-ssl-certificates-get')
        p = self.load_policy(
            {'name': 'one-lb-ssl-certificates',
             'resource': 'gcp.loadbalancing-ssl-certificate'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'testcert'})
        self.assertEqual(instance['kind'], 'compute#sslCertificate')
        self.assertEqual(instance['name'], 'testcert')


class LoadBalancingTargetHttpsProxyTest(BaseTest):

    def test_loadbalancing_target_https_proxy_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-target-https-proxies-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-target-https-proxies',
             'resource': 'gcp.loadbalancing-target-https-proxy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#targetHttpsProxy')
        self.assertEqual(resources[0]['name'], 'newhttpslb-target-proxy')

    def test_loadbalancing_target_https_proxy_get(self):
        factory = self.replay_flight_data('lb-target-https-proxies-get')
        p = self.load_policy(
            {'name': 'one-lb-target-https-proxies',
             'resource': 'gcp.loadbalancing-target-https-proxy'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'newhttpslb-target-proxy'})
        self.assertEqual(instance['kind'], 'compute#targetHttpsProxy')
        self.assertEqual(instance['name'], 'newhttpslb-target-proxy')


class LoadBalancingBackendBucketTest(BaseTest):

    def test_loadbalancing_backend_bucket_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-backend-buckets-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-backend-buckets',
             'resource': 'gcp.loadbalancing-backend-bucket'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#backendBucket')
        self.assertEqual(resources[0]['name'], 'newbucket')

    def test_loadbalancing_backend_bucket_get(self):
        factory = self.replay_flight_data('lb-backend-buckets-get')
        p = self.load_policy(
            {'name': 'one-lb-backend-buckets',
             'resource': 'gcp.loadbalancing-backend-bucket'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'newbucket'})
        self.assertEqual(instance['kind'], 'compute#backendBucket')
        self.assertEqual(instance['name'], 'newbucket')


class LoadBalancingHttpsHealthCheckTest(BaseTest):

    def test_loadbalancing_https_health_check_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-https-health-checks-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-https-health-checks',
             'resource': 'gcp.loadbalancing-https-health-check'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#httpsHealthCheck')
        self.assertEqual(resources[0]['name'], 'newhealthcheck')

    def test_loadbalancing_https_health_check_get(self):
        factory = self.replay_flight_data('lb-https-health-checks-get')
        p = self.load_policy(
            {'name': 'one-lb-https-health-checks',
             'resource': 'gcp.loadbalancing-https-health-check'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'newhealthcheck'})
        self.assertEqual(instance['kind'], 'compute#httpsHealthCheck')
        self.assertEqual(instance['name'], 'newhealthcheck')


class LoadBalancingHttpHealthCheckTest(BaseTest):

    def test_loadbalancing_http_health_check_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-http-health-checks-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-http-health-checks',
             'resource': 'gcp.loadbalancing-http-health-check'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#httpHealthCheck')
        self.assertEqual(resources[0]['name'], 'newhttphealthcheck')

    def test_loadbalancing_http_health_check_get(self):
        factory = self.replay_flight_data('lb-http-health-checks-get')
        p = self.load_policy(
            {'name': 'one-lb-http-health-checks',
             'resource': 'gcp.loadbalancing-http-health-check'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'newhttphealthcheck'})
        self.assertEqual(instance['kind'], 'compute#httpHealthCheck')
        self.assertEqual(instance['name'], 'newhttphealthcheck')


class LoadBalancingHealthCheckTest(BaseTest):

    def test_loadbalancing_health_check_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-health-checks-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-health-checks',
             'resource': 'gcp.loadbalancing-health-check'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#healthCheck')
        self.assertEqual(resources[0]['name'], 'new-tcp-health-check')

    def test_loadbalancing_health_check_get(self):
        factory = self.replay_flight_data('lb-health-checks-get')
        p = self.load_policy(
            {'name': 'one-lb-health-checks',
             'resource': 'gcp.loadbalancing-health-check'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'name': 'new-tcp-health-check'})
        self.assertEqual(instance['kind'], 'compute#healthCheck')
        self.assertEqual(instance['name'], 'new-tcp-health-check')
