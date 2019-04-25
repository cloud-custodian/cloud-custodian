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

import re

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo
from c7n.utils import local_session


@resources.register('appengine-app')
class AppEngineApp(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps'
        enum_spec = ('get', '[@]', None)
        scope = None
        id = 'id'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'appsId': re.compile('apps/(.*)').match(
                    resource_info['resourceName']).group(1)})

    def get_resource_query(self):
        return {'appsId': local_session(self.session_factory).get_default_project()}


@resources.register('appengine-certificate')
class AppEngineCertificate(ChildResourceManager):

    def _get_parent_resource_info(self, child_instance):
        return {'resourceName': re.compile(
            '(apps/.*?)/authorizedCertificates/.*').match(child_instance['name']).group(1)}

    class resource_type(ChildTypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps.authorizedCertificates'
        enum_spec = ('list', 'certificates[]', None)
        scope = None
        id = 'id'
        parent_spec = {
            'resource': 'appengine-app',
            'child_enum_params': {
                ('id', 'appsId')
            }
        }

        @staticmethod
        def get(client, resource_info):
            name_param_re = re.compile('apps/(.*?)/authorizedCertificates/(.*)')
            apps_id, cert_id = name_param_re.match(resource_info['resourceName']).groups()
            return client.execute_query('get', {'appsId': apps_id,
                                                'authorizedCertificatesId': cert_id})


@resources.register('appengine-domain')
class AppEngineDomain(ChildResourceManager):

    class resource_type(ChildTypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps.authorizedDomains'
        enum_spec = ('list', 'domains[]', None)
        scope = None
        id = 'id'
        parent_spec = {
            'resource': 'appengine-app',
            'child_enum_params': {
                ('id', 'appsId')
            }
        }


@resources.register('appengine-domain-mapping')
class AppEngineDomainMapping(ChildResourceManager):

    def _get_parent_resource_info(self, child_instance):
        return {'resourceName': re.compile(
            '(apps/.*?)/domainMappings/.*').match(child_instance['name']).group(1)}

    class resource_type(ChildTypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps.domainMappings'
        enum_spec = ('list', 'domainMappings[]', None)
        scope = None
        id = 'id'
        parent_spec = {
            'resource': 'appengine-app',
            'child_enum_params': {
                ('id', 'appsId')
            }
        }

        @staticmethod
        def get(client, resource_info):
            name_param_re = re.compile('apps/(.*?)/domainMappings/(.*)')
            apps_id, mapping_id = name_param_re.match(resource_info['resourceName']).groups()
            return client.execute_query('get', {'appsId': apps_id,
                                                'domainMappingsId': mapping_id})


@resources.register('appengine-firewall-ingress-rule')
class AppEngineFirewallIngressRule(ChildResourceManager):

    def _get_parent_resource_info(self, child_instance):
        return {'resourceName': 'apps/%s' %
                                local_session(self.session_factory).get_default_project()}

    class resource_type(ChildTypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps.firewall.ingressRules'
        enum_spec = ('list', 'ingressRules[]', None)
        scope = None
        id = 'id'
        parent_spec = {
            'resource': 'appengine-app',
            'child_enum_params': {
                ('id', 'appsId')
            }
        }

        @staticmethod
        def get(client, resource_info):
            rule_re = re.compile('apps/(.*?)/firewall/ingressRules/(.*)')
            apps_id, ingress_rules_id = rule_re.match(resource_info['resourceName']).groups()
            return client.execute_query(
                'get', {'appsId': apps_id,
                        'ingressRulesId': ingress_rules_id})
