# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from time import sleep
from gcp_common import BaseTest, event_data


class LoadBalancingAddressTest(BaseTest):

    def test_loadbalancer_address_query(self):
        factory = self.replay_flight_data('lb-addresses-query')
        p = self.load_policy(
            {'name': 'all-lb-addresses',
             'resource': 'gcp.loadbalancer-address'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#address')
        self.assertEqual(resources[0]['address'], '35.193.10.19')

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute:us-central1:cloud-custodian:address/new1',
            ],
        )

    def test_loadbalancer_address_get(self):
        factory = self.replay_flight_data('lb-addresses-get')
        p = self.load_policy(
            {'name': 'one-region-address',
             'resource': 'gcp.loadbalancer-address',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-addresses-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#address')
        self.assertEqual(instances[0]['address'], '35.202.198.74')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute:us-central1:cloud-custodian:address/custodian-address-1',
            ],
        )

    def test_loadbalancer_address_delete(self):
        region = 'us-central1'
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-addresses-delete',
                                          project_id=project_id)
        policy = self.load_policy(
            {'name': 'delete-address',
             'resource': 'gcp.loadbalancer-address',
             'actions': ['delete']
             }, session_factory=factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], 'new322')

        client = policy.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'region': region})

        self.assertEqual(len(result['items']["regions/{}".format(region)]['addresses']), 0)


class LoadBalancingUrlMapTest(BaseTest):

    def test_loadbalancer_url_map_query(self):
        factory = self.replay_flight_data('lb-url-maps-query')
        p = self.load_policy(
            {'name': 'all-lb-url-maps',
             'resource': 'gcp.loadbalancer-url-map'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#urlMap')
        self.assertEqual(resources[0]['fingerprint'], 'GMqHBoGzLDY=')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:url-map/lb',
            ],
        )

    def test_loadbalancer_url_map_get(self):
        factory = self.replay_flight_data('lb-url-maps-get')
        p = self.load_policy(
            {'name': 'one-lb-url-map',
             'resource': 'gcp.loadbalancer-url-map',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-url-maps-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#urlMap')
        self.assertEqual(instances[0]['fingerprint'], 'oA9r95u1zRI=')
        self.assertEqual(instances[0]['name'], 'custodian-load-balancer-0')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:url-map/custodian-load-balancer-0',
            ],
        )


class LoadBalancingTargetTcpProxyTest(BaseTest):

    def test_loadbalancer_target_tcp_proxy_query(self):
        factory = self.replay_flight_data('lb-target-tcp-proxies-query')
        p = self.load_policy(
            {'name': 'all-lb-target-tcp-proxies',
             'resource': 'gcp.loadbalancer-target-tcp-proxy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#targetTcpProxy')
        self.assertEqual(resources[0]['name'], 'newlb1-target-proxy')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:target-tcp-proxy/newlb1-target-proxy',
            ],
        )

    def test_loadbalancer_target_tcp_proxy_get(self):
        factory = self.replay_flight_data('lb-target-tcp-proxies-get')
        p = self.load_policy(
            {'name': 'one-lb-target-tcp-proxy',
             'resource': 'gcp.loadbalancer-target-tcp-proxy',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-target-tcp-proxy-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#targetTcpProxy')
        self.assertEqual(instances[0]['name'], 'target-tcp-proxy')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:target-tcp-proxy/target-tcp-proxy',
            ],
        )


class LoadBalancingTargetSslProxyTest(BaseTest):

    def test_loadbalancer_target_ssl_proxy_query(self):
        factory = self.replay_flight_data('lb-target-ssl-proxies-query')
        p = self.load_policy(
            {'name': 'all-lb-target-ssl-proxies',
             'resource': 'gcp.loadbalancer-target-ssl-proxy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#targetSslProxy')
        self.assertEqual(resources[0]['name'], 'lb2-target-proxy')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:target-ssl-proxy/lb2-target-proxy',
            ],
        )

    def test_loadbalancer_target_ssl_proxy_get(self):
        factory = self.replay_flight_data('lb-target-ssl-proxies-get')
        p = self.load_policy(
            {'name': 'one-lb-target-ssl-proxy',
             'resource': 'gcp.loadbalancer-target-ssl-proxy',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-target-ssl-proxy-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#targetSslProxy')
        self.assertEqual(instances[0]['name'], 'target-ssl-proxy')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:target-ssl-proxy/target-ssl-proxy',
            ],
        )


class LoadBalancingSslPolicyTest(BaseTest):

    def test_loadbalancer_ssl_policy_query(self):
        factory = self.replay_flight_data('lb-ssl-policies-query')
        p = self.load_policy(
            {'name': 'all-lb-ssl-policies',
             'resource': 'gcp.loadbalancer-ssl-policy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#sslPolicy')
        self.assertEqual(resources[0]['name'], 'newpolicy')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:ssl-policy/newpolicy',
            ],
        )

    def test_loadbalancer_ssl_policy_get(self):
        factory = self.replay_flight_data('lb-ssl-policies-get')
        p = self.load_policy(
            {'name': 'one-lb-ssl-policies',
             'resource': 'gcp.loadbalancer-ssl-policy',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-ssl-policy-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#sslPolicy')
        self.assertEqual(instances[0]['name'], 'custodian-ssl-policiy-0')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:ssl-policy/custodian-ssl-policiy-0',
            ],
        )

    def test_loadbalancer_ssl_policy_delete(self):
        project_id = 'custodian-test-project-0'
        session_factory = self.replay_flight_data('lb-ssl-policy-delete',
                                                  project_id=project_id)
        base_policy = {'name': 'lb-ssl-policy-delete',
                       'resource': 'gcp.loadbalancer-ssl-policy'}

        policy = self.load_policy(
            dict(base_policy,
                 filters=[{'type': 'value',
                           'key': 'minTlsVersion',
                           'op': 'ne',
                           'value': 'TLS_1_2'}],
                 actions=[{'type': 'delete'}]),
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(2, len(resources))
        self.assertIsNot('TLS_1_2', resources[0]['minTlsVersion'])
        self.assertIsNot('TLS_1_2', resources[1]['minTlsVersion'])

        if self.recording:
            sleep(1)

        client = policy.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id})
        items = result['items']
        self.assertEqual(1, len(items))
        self.assertEqual('TLS_1_2', items[0]['minTlsVersion'])


class LoadBalancingSslCertificateTest(BaseTest):

    def test_loadbalancer_ssl_certificate_query(self):
        factory = self.replay_flight_data('lb-ssl-certificates-query')
        p = self.load_policy(
            {'name': 'all-lb-ssl-certificates',
             'resource': 'gcp.loadbalancer-ssl-certificate'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#sslCertificate')
        self.assertEqual(resources[0]['name'], 'testcert')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:ssl-certificate/testcert',
            ],
        )

    def test_loadbalancer_ssl_certificate_get(self):
        factory = self.replay_flight_data('lb-ssl-certificates-get')
        p = self.load_policy(
            {'name': 'one-lb-ssl-certificates',
             'resource': 'gcp.loadbalancer-ssl-certificate',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-ssl-certificate-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#sslCertificate')
        self.assertEqual(instances[0]['name'], 'comelfo-com-google-certificate')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:ssl-certificate/comelfo-com-google-certificate',
            ],
        )


class LoadBalancingTargetHttpsProxyTest(BaseTest):

    def test_loadbalancer_target_https_proxy_query(self):
        factory = self.replay_flight_data('lb-target-https-proxies-query')
        p = self.load_policy(
            {'name': 'all-lb-target-https-proxies',
             'resource': 'gcp.loadbalancer-target-https-proxy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#targetHttpsProxy')
        self.assertEqual(resources[0]['name'], 'newhttpslb-target-proxy')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:target-https-proxy/newhttpslb-target-proxy',
            ],
        )

    def test_loadbalancer_target_https_proxy_get(self):
        factory = self.replay_flight_data('lb-target-https-proxies-get')
        p = self.load_policy(
            {'name': 'one-lb-target-https-proxies',
             'resource': 'gcp.loadbalancer-target-https-proxy',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-target-https-proxy-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#targetHttpsProxy')
        self.assertEqual(instances[0]['name'], 'custodian-https-target-proxy-0')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:target-https-proxy/custodian-https-target-proxy-0',
            ],
        )


class LoadBalancingBackendBucketTest(BaseTest):

    def test_loadbalancer_backend_bucket_query(self):
        factory = self.replay_flight_data('lb-backend-buckets-query')
        p = self.load_policy(
            {'name': 'all-lb-backend-buckets',
             'resource': 'gcp.loadbalancer-backend-bucket'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#backendBucket')
        self.assertEqual(resources[0]['name'], 'newbucket')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:backend-bucket/newbucket',
            ],
        )

    def test_loadbalancer_backend_bucket_get(self):
        factory = self.replay_flight_data('lb-backend-buckets-get')
        p = self.load_policy(
            {'name': 'one-lb-backend-buckets',
             'resource': 'gcp.loadbalancer-backend-bucket',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-backend-bucket-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#backendBucket')
        self.assertEqual(instances[0]['name'], 'custodian-backend-bucket-0')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:backend-bucket/custodian-backend-bucket-0',
            ],
        )

    def test_loadbalancer_backend_bucket_delete(self):
        project_id = 'cloud-custodian'
        session_factory = self.replay_flight_data('lb-backend-buckets-delete',
                                                  project_id=project_id)
        base_policy = {'name': 'lb-addresses-delete',
                       'resource': 'gcp.loadbalancer-backend-bucket'}

        policy = self.load_policy(
            dict(base_policy,
                 filters=[{'type': 'value',
                           'key': 'bucketName',
                           'op': 'eq',
                           'value': 'custodian-bucket-0'}],
                 actions=[{'type': 'delete'}]),
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(2, len(resources))
        self.assertEqual('custodian-bucket-0', resources[0]['bucketName'])
        self.assertEqual('custodian-bucket-0', resources[1]['bucketName'])
        self.assertEqual('custodian-backend-bucket-1', resources[0]['name'])
        self.assertEqual('custodian-backend-bucket-3', resources[1]['name'])

        if self.recording:
            sleep(5)

        client = policy.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id})
        items = result['items']
        self.assertEqual(1, len(items))
        self.assertIsNot('custodian-bucket-0', items[0]['bucketName'])
        self.assertEqual('custodian-backend-bucket-2', items[0]['name'])


class LoadBalancingHttpsHealthCheckTest(BaseTest):

    def test_loadbalancer_https_health_check_query(self):
        factory = self.replay_flight_data('lb-https-health-checks-query')
        p = self.load_policy(
            {'name': 'all-lb-https-health-checks',
             'resource': 'gcp.loadbalancer-https-health-check'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#httpsHealthCheck')
        self.assertEqual(resources[0]['name'], 'newhealthcheck')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:https-health-check/newhealthcheck',
            ],
        )

    def test_loadbalancer_https_health_check_get(self):
        factory = self.replay_flight_data('lb-https-health-checks-get')
        p = self.load_policy(
            {'name': 'one-lb-https-health-checks',
             'resource': 'gcp.loadbalancer-https-health-check',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-https-health-checks-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#httpsHealthCheck')
        self.assertEqual(instances[0]['name'], 'custodian-https-health-check')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:https-health-check/custodian-https-health-check',
            ],
        )


class LoadBalancingHttpHealthCheckTest(BaseTest):

    def test_loadbalancer_http_health_check_query(self):
        factory = self.replay_flight_data('lb-http-health-checks-query')
        p = self.load_policy(
            {'name': 'all-lb-http-health-checks',
             'resource': 'gcp.loadbalancer-http-health-check'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#httpHealthCheck')
        self.assertEqual(resources[0]['name'], 'newhttphealthcheck')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:http-health-check/newhttphealthcheck',
            ],
        )

    def test_loadbalancer_http_health_check_get(self):
        factory = self.replay_flight_data('lb-http-health-checks-get')
        p = self.load_policy(
            {'name': 'one-lb-http-health-checks',
             'resource': 'gcp.loadbalancer-http-health-check',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-http-health-checks-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#httpHealthCheck')
        self.assertEqual(instances[0]['name'], 'custodian-http-health-check')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:http-health-check/custodian-http-health-check',
            ],
        )


class LoadBalancingHealthCheckTest(BaseTest):

    def test_loadbalancer_health_check_query(self):
        factory = self.replay_flight_data('lb-health-checks-query')
        p = self.load_policy(
            {'name': 'all-lb-health-checks',
             'resource': 'gcp.loadbalancer-health-check'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#healthCheck')
        self.assertEqual(resources[0]['name'], 'new-tcp-health-check')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:health-check/new-tcp-health-check',
            ],
        )

    def test_loadbalancer_health_check_get(self):
        factory = self.replay_flight_data('lb-health-checks-get')
        p = self.load_policy(
            {'name': 'one-lb-health-checks',
             'resource': 'gcp.loadbalancer-health-check',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-health-checks-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#healthCheck')
        self.assertEqual(instances[0]['name'], 'custodain-health-check')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:health-check/custodain-health-check',
            ],
        )


class LoadBalancingTargetHttpProxyTest(BaseTest):

    def test_loadbalancer_target_http_proxy_query(self):
        factory = self.replay_flight_data('lb-target-http-proxies-query')
        p = self.load_policy(
            {'name': 'all-lb-target-http-proxies',
             'resource': 'gcp.loadbalancer-target-http-proxy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#targetHttpProxy')
        self.assertEqual(resources[0]['name'], 'new-proxy')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:target-http-proxy/new-proxy',
            ],
        )

    def test_loadbalancer_target_http_proxy_get(self):
        factory = self.replay_flight_data('lb-target-http-proxies-get')
        p = self.load_policy(
            {'name': 'one-lb-target-http-proxies',
             'resource': 'gcp.loadbalancer-target-http-proxy',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-target-http-proxies-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#targetHttpProxy')
        self.assertEqual(instances[0]['name'], 'custodian-load-balancer-0-target-proxy')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:target-http-proxy/custodian-load-balancer-0-target-proxy',  # noqa: E501
            ],
        )


class LoadBalancingBackendServiceTest(BaseTest):

    def test_loadbalancer_backend_service_query(self):
        factory = self.replay_flight_data('lb-backend-services-query')
        p = self.load_policy(
            {'name': 'all-lb-backend-services',
             'resource': 'gcp.loadbalancer-backend-service'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#backendService')
        self.assertEqual(resources[0]['name'], 'new-backend-service')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:backend-service/new-backend-service',
            ],
        )

    def test_loadbalancer_backend_service_get(self):
        factory = self.replay_flight_data('lb-backend-services-get')
        p = self.load_policy(
            {'name': 'one-lb-backend-services',
             'resource': 'gcp.loadbalancer-backend-service',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-backend-services-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#backendService')
        self.assertEqual(instances[0]['name'], 'common-backend-service-0')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:backend-service/common-backend-service-0',
            ],
        )


class LoadBalancingTargetInstanceTest(BaseTest):

    def test_loadbalancer_target_instance_query(self):
        factory = self.replay_flight_data('lb-target-instances-query')
        p = self.load_policy(
            {'name': 'all-lb-target-instances',
             'resource': 'gcp.loadbalancer-target-instance'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#targetInstance')
        self.assertEqual(resources[0]['name'], 'new-target-instance')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute:us-central1-a:cloud-custodian:target-instance/new-target-instance',
            ],
        )

    def test_loadbalancer_target_instance_get(self):
        factory = self.replay_flight_data('lb-target-instances-get')
        p = self.load_policy(
            {'name': 'one-lb-target-instances',
             'resource': 'gcp.loadbalancer-target-instance',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-target-instances-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#targetInstance')
        self.assertEqual(instances[0]['name'], 'custodian-target-instance-1')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute:us-central1-c:cloud-custodian:target-instance/custodian-target-instance-1',  # noqa: E501
            ],
        )


class LoadBalancingTargetPoolTest(BaseTest):

    def test_loadbalancer_target_pool_query(self):
        factory = self.replay_flight_data('lb-target-pools-query')
        p = self.load_policy(
            {'name': 'all-lb-target-pools',
             'resource': 'gcp.loadbalancer-target-pool'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#targetPool')
        self.assertEqual(resources[0]['name'], 'new-target-pool')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute:us-central1:cloud-custodian:target-pool/new-target-pool',
            ],
        )

    def test_loadbalancer_target_pool_get(self):
        factory = self.replay_flight_data('lb-target-pools-get')
        p = self.load_policy(
            {'name': 'one-lb-target-pools',
             'resource': 'gcp.loadbalancer-target-pool',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-target-pools-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#targetPool')
        self.assertEqual(instances[0]['name'], 'custodian-target-pool-0')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute:us-central1:cloud-custodian:target-pool/custodian-target-pool-0',
            ],
        )


class LoadBalancingForwardingRuleTest(BaseTest):

    def test_loadbalancer_forwarding_rule_query(self):
        factory = self.replay_flight_data('lb-forwarding-rules-query')
        p = self.load_policy(
            {'name': 'all-lb-forwarding-rules',
             'resource': 'gcp.loadbalancer-forwarding-rule'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#forwardingRule')
        self.assertEqual(resources[0]['name'], 'new-fe')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute:us-central1:cloud-custodian:forwarding-rule/new-fe',
            ],
        )

    def test_loadbalancer_forwarding_rule_get(self):
        factory = self.replay_flight_data('lb-forwarding-rules-get')
        p = self.load_policy(
            {'name': 'one-lb-forwarding-rules',
             'resource': 'gcp.loadbalancer-forwarding-rule',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-forwarding-rules-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#forwardingRule')
        self.assertEqual(instances[0]['name'], 'custodian-frontend-tcp-0')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute:us-central1:cloud-custodian:forwarding-rule/custodian-frontend-tcp-0',
            ],
        )


class LoadBalancingGlobalForwardingRuleTest(BaseTest):

    def test_loadbalancer_global_forwarding_rule_query(self):
        factory = self.replay_flight_data('lb-global-forwarding-rules-query')
        p = self.load_policy(
            {'name': 'all-lb-global-forwarding-rules',
             'resource': 'gcp.loadbalancer-global-forwarding-rule'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#forwardingRule')
        self.assertEqual(resources[0]['name'], 'new-global-frontend')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:global-forwarding-rule/new-global-frontend',
            ],
        )

    def test_loadbalancer_global_forwarding_rule_get(self):
        factory = self.replay_flight_data('lb-global-forwarding-rules-get')
        p = self.load_policy(
            {'name': 'one-lb-global-forwarding-rules',
             'resource': 'gcp.loadbalancer-global-forwarding-rule',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-global-forwarding-rules-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#forwardingRule')
        self.assertEqual(instances[0]['name'], 'custodian-frontend-0')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:global-forwarding-rule/custodian-frontend-0',
            ],
        )


class LoadBalancingGlobalAddressTest(BaseTest):

    def test_loadbalancer_global_address_query(self):
        factory = self.replay_flight_data('lb-global-addresses-query')
        p = self.load_policy(
            {'name': 'all-lb-global-addresses',
             'resource': 'gcp.loadbalancer-global-address'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#address')
        self.assertEqual(resources[0]['name'], 'new-global-address')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:global-address/new-global-address',
            ],
        )

    def test_loadbalancer_global_address_get(self):
        factory = self.replay_flight_data('lb-global-addresses-get')
        p = self.load_policy(
            {'name': 'one-lb-global-addresses',
             'resource': 'gcp.loadbalancer-global-address',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('lb-global-addresses-get.json')
        instances = exec_mode.run(event, None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]['kind'], 'compute#address')
        self.assertEqual(instances[0]['name'], 'custodian-global-address-0')
        self.assertEqual(
            p.resource_manager.get_urns(instances),
            [
                'gcp:compute::cloud-custodian:global-address/custodian-global-address-0',
            ],
        )
