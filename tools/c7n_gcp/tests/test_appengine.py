# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import functools

import pytest
from c7n_gcp.client import ServiceClient, Session
from c7n_gcp.resources.appengine import parse_version_name
from gcp_common import BaseTest, audit_event_recorder, event_data
from pytest_terraform import terraform


class AppEngineAppTest(BaseTest):

    def test_app_query(self):
        project_id = self.project_id
        app_name = 'apps/{}'.format(project_id)
        session_factory = self.replay_flight_data(
            'app-engine-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-dryrun',
             'resource': 'gcp.app-engine'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], app_name)

        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [f"gcp:appengine:europe-west3:{project_id}:app/{project_id}"],
        )

    def test_app_get(self):
        project_id = self.project_id
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

        self.assertEqual(
            policy.resource_manager.get_urns([resource]),
            [f"gcp:appengine:europe-west3:{project_id}:app/{project_id}"],
        )


class AppEngineCertificateTest(BaseTest):

    def test_certificate_query(self):
        project_id = self.project_id
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

        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [f"gcp:appengine:europe-west3:{project_id}:certificate/12277184"],
        )

    def test_certificate_get(self):
        project_id = self.project_id
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

        self.assertEqual(
            policy.resource_manager.get_urns([resource]),
            [f"gcp:appengine:europe-west3:{project_id}:certificate/12277184"],
        )


class AppEngineDomainTest(BaseTest):

    def test_domain_query(self):
        project_id = self.project_id
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

        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [f"gcp:appengine:europe-west3:{project_id}:domain/gcp-li.ga"],
        )


class AppEngineDomainMappingTest(BaseTest):

    def test_domain_mapping_query(self):
        project_id = self.project_id
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

        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [f"gcp:appengine:europe-west3:{project_id}:domain-mapping/alex.gcp-li.ga"],
        )

    def test_domain_mapping_get(self):
        project_id = self.project_id
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

        self.assertEqual(
            policy.resource_manager.get_urns([resource]),
            [f"gcp:appengine:europe-west3:{project_id}:domain-mapping/alex.gcp-li.ga"],
        )


class AppEngineFirewallIngressRuleTest(BaseTest):

    def test_firewall_ingress_rule_query(self):
        project_id = self.project_id
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

        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [f"gcp:appengine:europe-west3:{project_id}:firewall-ingress-rule/2147483647"],
        )

    def test_firewall_ingress_rule_get(self):
        project_id = self.project_id
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

        self.assertEqual(
            policy.resource_manager.get_urns([resource]),
            [f"gcp:appengine:europe-west3:{project_id}:firewall-ingress-rule/2147483647"],
        )


class AppEngineServiceTest(BaseTest):

    def test_service_query(self):
        project_id = self.project_id
        app_name = 'apps/{}'.format(project_id)
        service_id = '12277184'
        service_name = '{}/services/{}'.format(app_name, service_id)
        session_factory = self.replay_flight_data(
            'app-engine-service-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-service-run',
             'resource': 'gcp.app-engine-service'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resources = policy.run()
        self.assertEqual(resources[0]['name'], service_name)
        self.assertEqual(resources[0][parent_annotation_key]['name'], app_name)

        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [f"gcp:appengine:europe-west3:{project_id}:service/12277184"],
        )

    def test_service_get(self):
        project_id = self.project_id
        app_name = 'apps/' + project_id
        service_id = '12277184'
        service_name = '{}/services/{}'.format(app_name, service_id)
        session_factory = self.replay_flight_data(
            'app-engine-service-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-service-run',
             'resource': 'gcp.app-engine-service'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resource = policy.resource_manager.get_resource(
            {'resourceName': service_name})
        self.assertEqual(resource['name'], service_name)
        self.assertEqual(resource[parent_annotation_key]['name'], app_name)

        self.assertEqual(
            policy.resource_manager.get_urns([resource]),
            [f"gcp:appengine:europe-west3:{project_id}:service/12277184"],
        )


class AppEngineServiceVersionTest(BaseTest):

    def test_service_version(self):
        project_id = self.project_id
        app_name = 'apps/{}'.format(project_id)
        service_id = '12277184'
        version_id = 'v3'
        service_name = '{}/services/{}'.format(app_name, service_id)
        version = '{}/services/{}/versions/{}'.format(app_name, service_id, version_id)
        session_factory = self.replay_flight_data(
            'app-engine-service-version', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-service-version-run',
             'resource': 'gcp.app-engine-service-version'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resources = policy.run()
        self.assertEqual(resources[0]['name'], version)
        self.assertEqual(resources[0][parent_annotation_key]['name'], service_name)


def catch_all_security_levels(version):
    return [h['securityLevel'] for h in version['handlers'] if h['urlRegex'] == '/.*']


def capture_query_args(test, method):
    """Record the arguments of every ServiceClient ``method`` call.

    Replay matches flight files by URL path alone, so recorded handlers come back
    whether or not the request asked for them. Check the request instead.
    """
    captured = []
    query = getattr(ServiceClient, method)

    def record(client, verb, verb_arguments):
        captured.append(verb_arguments)
        return query(client, verb, verb_arguments)

    test.patch(ServiceClient, method, record)
    return captured


@terraform('app_engine_service_version', scope='session')
def test_app_engine_service_version_full_view(test, app_engine_service_version):
    always = app_engine_service_version[
        'google_app_engine_standard_app_version.secure_always.name']
    optional = app_engine_service_version[
        'google_app_engine_standard_app_version.secure_optional.name']
    factory = test.replay_flight_data('app_engine_service_version_full_view')
    list_args = capture_query_args(test, 'execute_paged_query')
    policy = test.load_policy(
        {'name': 'gcp-app-engine-service-version-full-view',
         'resource': 'gcp.app-engine-service-version'},
        session_factory=factory)

    versions = {v['name']: v for v in policy.run()}

    version_lists = [args for args in list_args if 'servicesId' in args]
    assert version_lists
    assert all(args.get('view') == 'FULL' for args in version_lists)
    assert catch_all_security_levels(versions[always]) == ['SECURE_ALWAYS']
    assert catch_all_security_levels(versions[optional]) == ['SECURE_OPTIONAL']


@terraform('app_engine_service_version', scope='session')
def test_app_engine_service_version_audit(test, app_engine_service_version):
    name = app_engine_service_version[
        'google_app_engine_standard_app_version.secure_always.name']
    factory = test.replay_flight_data('app_engine_service_version_audit')

    if test.recording:
        setup_session_factory = functools.partial(Session, project_id=test.project_id)
        audit_event_recorder(
            setup_session_factory,
            'app-engine-version-create.json',
            method='CreateVersion',
            resource_name=name,
            start_time_skew_seconds=900,
        ).record()
        # Otherwise the policy reuses the cached setup session and records nothing.
        test.cleanUp()

    get_args = capture_query_args(test, 'execute_query')
    policy = test.load_policy(
        {'name': 'gcp-app-engine-service-version-audit',
         'resource': 'gcp.app-engine-service-version',
         'mode': {
             'type': 'gcp-audit',
             'methods': ['google.appengine.v1.Versions.CreateVersion']}},
        session_factory=factory)
    exec_mode = policy.get_execution_mode()
    parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()
    service = name.rsplit('/versions/', 1)[0]

    for event_file in ('app-engine-version-create-first.json',
                       'app-engine-version-create-last.json'):
        [version] = exec_mode.run(event_data(event_file), None)
        assert version['name'] == name, event_file
        assert catch_all_security_levels(version) == ['SECURE_ALWAYS'], event_file
        assert version[parent_annotation_key]['name'] == service, event_file

    version_gets = [args for args in get_args if 'versionsId' in args]
    assert len(version_gets) == 2
    assert all(args.get('view') == 'FULL' for args in version_gets)


def test_parse_version_name_rejects_service_name():
    with pytest.raises(ValueError, match='apps/cloud-custodian/services/default'):
        parse_version_name('apps/cloud-custodian/services/default')
