# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class AppEngineAppTest(BaseTest):

    def test_app_query(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/{}'.format(project_id)
        session_factory = self.replay_flight_data(
            'app-engine-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-dryrun',
             'resource': 'gcp.app-engine'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], app_name)

    def test_app_get(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/' + project_id
        session_factory = self.replay_flight_data(
            'app-engine-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-dryrun',
             'resource': 'gcp.app-engine'},
            session_factory=session_factory)

        resource = policy.resource_manager.get_resource(
            {'resourceName': app_name})
        self.assertEqual(resource['name'], app_name)


class AppEngineCertificateTest(BaseTest):

    def test_certificate_query(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/{}'.format(project_id)
        certificate_id = '12277184'
        certificate_name = '{}/authorizedCertificates/{}'.format(app_name, certificate_id)
        session_factory = self.replay_flight_data(
            'app-engine-certificate-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-certificate-dryrun',
             'resource': 'gcp.app-engine-certificate'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resources = policy.run()
        self.assertEqual(resources[0]['name'], certificate_name)
        self.assertEqual(resources[0][parent_annotation_key]['name'], app_name)

    def test_certificate_get(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/' + project_id
        certificate_id = '12277184'
        certificate_name = '{}/authorizedCertificates/{}'.format(app_name, certificate_id)
        session_factory = self.replay_flight_data(
            'app-engine-certificate-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-certificate-dryrun',
             'resource': 'gcp.app-engine-certificate'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resource = policy.resource_manager.get_resource(
            {'resourceName': certificate_name})
        self.assertEqual(resource['name'], certificate_name)
        self.assertEqual(resource[parent_annotation_key]['name'], app_name)


class AppEngineDomainTest(BaseTest):

    def test_domain_query(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/{}'.format(project_id)
        domain_id = 'gcp-li.ga'
        domain_name = '{}/authorizedDomains/{}'.format(app_name, domain_id)
        session_factory = self.replay_flight_data(
            'app-engine-domain-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-domain-dryrun',
             'resource': 'gcp.app-engine-domain'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resources = policy.run()
        self.assertEqual(resources[0]['name'], domain_name)
        self.assertEqual(resources[0][parent_annotation_key]['name'], app_name)


class AppEngineDomainMappingTest(BaseTest):

    def test_domain_mapping_query(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/{}'.format(project_id)
        domain_mapping_id = 'alex.gcp-li.ga'
        domain_mapping_name = '{}/domainMappings/{}'.format(app_name, domain_mapping_id)
        session_factory = self.replay_flight_data(
            'app-engine-domain-mapping-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-domain-mapping-dryrun',
             'resource': 'gcp.app-engine-domain-mapping'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resources = policy.run()
        self.assertEqual(resources[0]['name'], domain_mapping_name)
        self.assertEqual(resources[0][parent_annotation_key]['name'], app_name)

    def test_domain_mapping_get(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/' + project_id
        domain_mapping_id = 'alex.gcp-li.ga'
        domain_mapping_name = '{}/domainMappings/{}'.format(app_name, domain_mapping_id)
        session_factory = self.replay_flight_data(
            'app-engine-domain-mapping-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-domain-mapping-dryrun',
             'resource': 'gcp.app-engine-domain-mapping'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resource = policy.resource_manager.get_resource(
            {'resourceName': domain_mapping_name})
        self.assertEqual(resource['name'], domain_mapping_name)
        self.assertEqual(resource[parent_annotation_key]['name'], app_name)


class AppEngineFirewallIngressRuleTest(BaseTest):

    def test_firewall_ingress_rule_query(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/{}'.format(project_id)
        rule_priority = 2147483647
        session_factory = self.replay_flight_data(
            'app-engine-firewall-ingress-rule-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-firewall-ingress-rule-dryrun',
             'resource': 'gcp.app-engine-firewall-ingress-rule'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resources = policy.run()
        self.assertEqual(resources[0]['priority'], rule_priority)
        self.assertEqual(resources[0][parent_annotation_key]['name'], app_name)

    def test_firewall_ingress_rule_get(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/{}'.format(project_id)
        rule_priority = 2147483647
        rule_priority_full = '{}/firewall/ingressRules/{}'.format(app_name, rule_priority)
        session_factory = self.replay_flight_data(
            'app-engine-firewall-ingress-rule-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-firewall-ingress-rule-dryrun',
             'resource': 'gcp.app-engine-firewall-ingress-rule'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resource = policy.resource_manager.get_resource(
            {'resourceName': rule_priority_full})
        self.assertEqual(resource['priority'], rule_priority)
        self.assertEqual(resource[parent_annotation_key]['name'], app_name)
