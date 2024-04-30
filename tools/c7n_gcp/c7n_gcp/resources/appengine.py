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
            'id', 'locationId', 'servingStatus', 'authDomain', 'defaultHostname']
        asset_type = "appengine.googleapis.com/Application"
        permissions = ('appengine.applications.get',)
        metric_key = 'resource.labels.module_id'
        urn_component = "app"
        urn_region_key = "locationId"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'appsId': re.match('apps/(.*)',
                    resource_info['resourceName']).group(1)})

    def get_resource_query(self):
        return {'appsId': local_session(self.session_factory).get_default_project()}


class AppEngineChildTypeInfo(ChildTypeInfo):
    service = 'appengine'
    version = 'v1'
    scope = None
    parent_spec = {
        'resource': 'app-engine',
        'child_enum_params': {
            ('id', 'appsId')
        }
    }
    permissions = ('appengine.applications.get',)

    @classmethod
    def _get_location(cls, resource):
        "Get the region from the parent."
        return cls.get_parent(resource)["locationId"]


@resources.register('app-engine-certificate')
class AppEngineCertificate(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.authorizedCertificates
    """
    def _get_parent_resource_info(self, child_instance):
        return {'resourceName': re.match(
            '(apps/.*?)/authorizedCertificates/.*', child_instance['name']).group(1)}

    class resource_type(AppEngineChildTypeInfo):
        component = 'apps.authorizedCertificates'
        enum_spec = ('list', 'certificates[]', None)
        name = 'displayName'
        id = 'id'
        default_report_fields = ['displayName', 'expireTime']
        urn_component = "certificate"

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
    class resource_type(AppEngineChildTypeInfo):
        component = 'apps.authorizedDomains'
        enum_spec = ('list', 'domains[]', None)
        id = 'id'
        name = "name"
        default_report_fields = [id, name]
        urn_component = "domain"


@resources.register('app-engine-domain-mapping')
class AppEngineDomainMapping(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.domainMappings
    """
    def _get_parent_resource_info(self, child_instance):
        return {'resourceName': re.match(
            '(apps/.*?)/domainMappings/.*', child_instance['name']).group(1)}

    class resource_type(AppEngineChildTypeInfo):
        component = 'apps.domainMappings'
        enum_spec = ('list', 'domainMappings[]', None)
        name = "name"
        id = 'id'
        default_report_fields = [id, name]
        urn_component = "domain-mapping"

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

    class resource_type(AppEngineChildTypeInfo):
        component = 'apps.firewall.ingressRules'
        enum_spec = ('list', 'ingressRules[]', None)
        name = id = 'priority'
        default_report_fields = ['priority', 'action', 'sourceRange', 'description']
        urn_component = "firewall-ingress-rule"

        @staticmethod
        def get(client, resource_info):
            apps_id, ingress_rules_id = re.match('apps/(.*?)/firewall/ingressRules/(.*)',
                                                 resource_info['resourceName']).groups()
            return client.execute_query(
                'get', {'appsId': apps_id,
                        'ingressRulesId': ingress_rules_id})


@resources.register('app-engine-service')
class AppEngineService(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.services
    """
    def _get_parent_resource_info(self, child_instance):
        return {'resourceName': re.match(
            '(apps/.*?)/services/.*', child_instance['name']).group(1)}

    class resource_type(AppEngineChildTypeInfo):
        component = 'apps.services'
        enum_spec = ('list', 'services[]', None)
        name = 'name'
        id = 'id'
        default_report_fields = ['name', 'networkSettings']
        urn_component = "service"
        asset_type = "appengine.googleapis.com/Service"

        @staticmethod
        def get(client, resource_info):
            apps_id, service_id = re.match('apps/(.*?)/services/(.*)',
                                           resource_info['resourceName']).groups()
            return client.execute_query('get', {'appsId': apps_id,
                                        'servicesId': service_id})


@resources.register('app-engine-service-version')
class AppEngineServiceVersion(ChildResourceManager):
    """GCP Resource
    https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.services.versions
    """

    class resource_type(AppEngineChildTypeInfo):
        component = 'apps.services.versions'
        name = 'name'
        id = 'id'
        enum_spec = ('list', 'versions[]', None)
        default_report_fields = ['name', 'instanceClass', 'runtime', 'runtimeChannel', 'vm']
        urn_component = "versions"
        asset_type = "appengine.googleapis.com/Version"
        parent_spec = {
            'resource': 'app-engine-service',
            'child_enum_params': [
                ('id', 'servicesId'),
                ('name', 'appsId', 'regex', r'/(.*?)/')
            ]
        }
