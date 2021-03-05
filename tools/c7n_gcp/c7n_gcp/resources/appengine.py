# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import re

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo
from c7n.utils import local_session


@resources.register('app-engine')
class AppEngineApp(QueryResourceManager):
    """GCP resource: https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps
    """
    class resource_type(TypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps'
        enum_spec = ('get', '[@]', None)
        scope = None
        id = 'id'
        name = 'name'
        default_report_fields = [
            'id', 'locationId', 'servingStatus', 'authDomain', 'defaultHostName']
        asset_type = "appengine.googleapis.com/Application"
        permissions = ('appengine.applications.get',)

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'appsId': re.match('apps/(.*)',
                    resource_info['resourceName']).group(1)})

    def get_resource_query(self):
        return {'appsId': local_session(self.session_factory).get_default_project()}


@resources.register('app-engine-certificate')
class AppEngineCertificate(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.authorizedCertificates
    """
    def _get_parent_resource_info(self, child_instance):
        return {'resourceName': re.match(
            '(apps/.*?)/authorizedCertificates/.*', child_instance['name']).group(1)}

    class resource_type(ChildTypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps.authorizedCertificates'
        enum_spec = ('list', 'certificates[]', None)
        scope = None
        name = 'displayName'
        id = 'id'
        parent_spec = {
            'resource': 'app-engine',
            'child_enum_params': {
                ('id', 'appsId')
            }
        }
        default_report_fields = ['displayName', 'expireTime']
        permissions = ('appengine.applications.get',)

        @staticmethod
        def get(client, resource_info):
            apps_id, cert_id = re.match('apps/(.*?)/authorizedCertificates/(.*)',
                                        resource_info['resourceName']).groups()
            return client.execute_query('get', {'appsId': apps_id,
                                                'authorizedCertificatesId': cert_id})


@resources.register('app-engine-domain')
class AppEngineDomain(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.authorizedDomains/list#AuthorizedDomain
    """
    class resource_type(ChildTypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps.authorizedDomains'
        enum_spec = ('list', 'domains[]', None)
        scope = None
        id = 'id'
        name = "name"
        default_report_fields = [id, name]
        parent_spec = {
            'resource': 'app-engine',
            'child_enum_params': {
                ('id', 'appsId')
            }
        }
        permissions = ('appengine.applications.get',)


@resources.register('app-engine-domain-mapping')
class AppEngineDomainMapping(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.domainMappings
    """
    def _get_parent_resource_info(self, child_instance):
        return {'resourceName': re.match(
            '(apps/.*?)/domainMappings/.*', child_instance['name']).group(1)}

    class resource_type(ChildTypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps.domainMappings'
        enum_spec = ('list', 'domainMappings[]', None)
        scope = None
        name = "name"
        id = 'id'
        default_report_fields = [id, name]
        parent_spec = {
            'resource': 'app-engine',
            'child_enum_params': {
                ('id', 'appsId')
            }
        }
        permissions = ('appengine.applications.get',)

        @staticmethod
        def get(client, resource_info):
            apps_id, mapping_id = re.match('apps/(.*?)/domainMappings/(.*)',
                                           resource_info['resourceName']).groups()
            return client.execute_query('get', {'appsId': apps_id,
                                                'domainMappingsId': mapping_id})


@resources.register('app-engine-firewall-ingress-rule')
class AppEngineFirewallIngressRule(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.firewall.ingressRules
    """
    def _get_parent_resource_info(self, child_instance):
        return {'resourceName': 'apps/%s' %
                                local_session(self.session_factory).get_default_project()}

    class resource_type(ChildTypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps.firewall.ingressRules'
        enum_spec = ('list', 'ingressRules[]', None)
        scope = None
        name = id = 'priority'
        parent_spec = {
            'resource': 'app-engine',
            'child_enum_params': {
                ('id', 'appsId')
            }
        }
        default_report_fields = ['priority', 'action', 'sourceRange', 'description']
        permissions = ('appengine.applications.get',)

        @staticmethod
        def get(client, resource_info):
            apps_id, ingress_rules_id = re.match('apps/(.*?)/firewall/ingressRules/(.*)',
                                                 resource_info['resourceName']).groups()
            return client.execute_query(
                'get', {'appsId': apps_id,
                        'ingressRulesId': ingress_rules_id})
