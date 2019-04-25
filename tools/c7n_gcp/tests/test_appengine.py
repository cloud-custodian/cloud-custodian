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


class AppEngineAppTest(BaseTest):

    def test_app_query(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/{}'.format(project_id)
        session_factory = self.replay_flight_data(
            'appengine-app-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-appengine-app-dryrun',
             'resource': 'gcp.appengine-app'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], app_name)

    def test_app_get(self):
        project_id = 'cloud-custodian'
        app_name = 'apps/' + project_id
        session_factory = self.replay_flight_data(
            'appengine-app-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-appengine-app-dryrun',
             'resource': 'gcp.appengine-app'},
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
            'appengine-certificate-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-appengine-certificate-dryrun',
             'resource': 'gcp.appengine-certificate'},
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
            'appengine-certificate-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-appengine-certificate-dryrun',
             'resource': 'gcp.appengine-certificate'},
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
            'appengine-domain-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-appengine-domain-dryrun',
             'resource': 'gcp.appengine-domain'},
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
            'appengine-domain-mapping-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-appengine-domain-mapping-dryrun',
             'resource': 'gcp.appengine-domain-mapping'},
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
            'appengine-domain-mapping-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-appengine-domain-mapping-dryrun',
             'resource': 'gcp.appengine-domain-mapping'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()

        resource = policy.resource_manager.get_resource(
            {'resourceName': domain_mapping_name})
        self.assertEqual(resource['name'], domain_mapping_name)
        self.assertEqual(resource[parent_annotation_key]['name'], app_name)
