# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re
from c7n.utils import type_schema, local_session, jmespath_search
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo


@resources.register('loadbalancer-address')
class LoadBalancingAddress(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/addresses
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'addresses'
        enum_spec = ('aggregatedList', 'items.*.addresses[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            name, "description", "address", "status", "region", "addressType"
        ]
        asset_type = "compute.googleapis.com/Address"
        urn_component = "address"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'region': resource_info['location'],
                'address': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@LoadBalancingAddress.action_registry.register('delete')
class LoadBalancingAddressDelete(MethodAction):
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    attr_filter = ('status', ('RESERVED',))

    def get_resource_params(self, model, resource):
        project = local_session(self.manager.source.query.session_factory).get_default_project()
        return {
            'project': project,
            'region': resource['region'].rsplit('/', 1)[-1],
            'address': resource['name']}

    def filter_resources(self, resources):
        resources = super().filter_resources(resources)
        missing_region = [r for r in resources if 'region' not in r]
        if missing_region:
            removed = ', '.join([r.get('name', '<unknown>') for r in missing_region])
            self.log.warning(
                "policy:%s action:%s filtered out %d resources without region: %s",
                self.manager.ctx.policy.name,
                self.type,
                len(missing_region),
                removed,
            )
            resources = [r for r in resources if 'region' in r]

        return resources


@resources.register('loadbalancer-url-map')
class LoadBalancingUrlMap(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/urlMaps
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'urlMaps'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "region", "defaultService"
        ]
        asset_type = "compute.googleapis.com/UrlMap"
        urn_component = "url-map"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'urlMap': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-target-tcp-proxy')
class LoadBalancingTargetTcpProxy(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/targetTcpProxies
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetTcpProxies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "service"
        ]
        asset_type = "compute.googleapis.com/TargetTcpProxy"
        urn_component = "target-tcp-proxy"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'targetTcpProxy': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-target-ssl-proxy')
class LoadBalancingTargetSslProxy(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/targetSslProxies
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetSslProxies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "service", "sslPolicy"
        ]
        asset_type = "compute.googleapis.com/TargetSslProxy"
        urn_component = "target-ssl-proxy"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'targetSslProxy': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-ssl-policy')
class LoadBalancingSslPolicy(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/sslPolicies
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'sslPolicies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "profile", "minTlsVersion"
        ]
        urn_component = "ssl-policy"
        asset_type = "compute.googleapis.com/SslPolicy"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'sslPolicy': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@LoadBalancingSslPolicy.action_registry.register('delete')
class LoadBalancingSslPolicyDelete(MethodAction):
    """The action is used for Load Balancing SSL Policies delete.
    GCP action is https://cloud.google.com/compute/docs/reference/rest/v1/sslPolicies/delete.

    Example:

    .. code-block:: yaml

        policies:
          - name: gcp-load-balancing-ssl-policies-delete
            resource: gcp.loadbalancer-ssl-policy
            filters:
              - type: value
                key: minTlsVersion
                op: ne
                value: TLS_1_2
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, model, resource):
        project = local_session(self.manager.source.query.session_factory).get_default_project()
        return {
            'project': project,
            'sslPolicy': resource['name']}


@resources.register('loadbalancer-ssl-certificate')
class LoadBalancingSslCertificate(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/sslCertificates
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'sslCertificates'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "type", "region", "expireTime"
        ]
        asset_type = "compute.googleapis.com/SslCertificate"
        urn_component = "ssl-certificate"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'sslCertificate': resource_info['ssl_certificate_name']})


@resources.register('loadbalancer-target-https-proxy')
class LoadBalancingTargetHttpsProxy(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpsProxies
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetHttpsProxies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            name, "description", "creationTimestamp", "sslPolicy", "urlMap"
        ]
        asset_type = "compute.googleapis.com/TargetHttpsProxy"
        scc_type = "google.compute.TargetHttpsProxy"
        urn_component = "target-https-proxy"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'targetHttpsProxy': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-backend-bucket')
class LoadBalancingBackendBucket(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/backendBuckets
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'backendBuckets'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "bucketName", "enableCdn"
        ]
        asset_type = "compute.googleapis.com/BackendBucket"
        urn_component = "backend-bucket"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'backendBucket': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@LoadBalancingBackendBucket.action_registry.register('delete')
class LoadBalancingBackendBucketDelete(MethodAction):
    """The action is used for Load Balancing Backend Buckets delete.
    GCP action is https://cloud.google.com/compute/docs/reference/rest/v1/backendBuckets/delete.

    Example:

    .. code-block:: yaml

        policies:
          - name: gcp-loadbalancer-backend-buckets-delete
            resource: gcp.loadbalancer-backend-bucket
            filters:
              - type: value
                key: bucketName
                op: eq
                value: custodian-bucket-0
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, model, resource):
        project = local_session(self.manager.source.query.session_factory).get_default_project()
        return {
            'project': project,
            'backendBucket': resource['name']}


@resources.register('loadbalancer-https-health-check')
class LoadBalancingHttpsHealthCheck(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/httpsHealthChecks
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'httpsHealthChecks'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            name, "description", "host", "port", "requestPath", "checkIntervalSec"]
        asset_type = "compute.googleapis.com/HttpsHealthCheck"
        urn_component = "https-health-check"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'httpsHealthCheck': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-http-health-check')
class LoadBalancingHttpHealthCheck(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/httpHealthChecks
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'httpHealthChecks'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            name, "description", "host", "port", "requestPath", "checkIntervalSec"]
        asset_type = "compute.googleapis.com/HttpHealthCheck"
        urn_component = "http-health-check"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'httpHealthCheck': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-health-check')
class LoadBalancingHealthCheck(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/healthChecks
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'healthChecks'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "checkIntervalSec",
            "healthyThreshold", "unhealthyThreshold", "timeoutSec"]
        asset_type = "compute.googleapis.com/HealthCheck"
        urn_component = "health-check"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'healthCheck': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-target-http-proxy')
class LoadBalancingTargetHttpProxy(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpProxies
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetHttpProxies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "region", "urlMap"]
        asset_type = "compute.googleapis.com/TargetHttpProxy"
        urn_component = "target-http-proxy"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'targetHttpProxy': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-backend-service')
class LoadBalancingBackendService(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/backendServices
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'backendServices'
        enum_spec = ('aggregatedList', 'items.*.backendServices[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "region", "network"]
        asset_type = "compute.googleapis.com/BackendService"
        urn_component = "backend-service"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'backendService': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-target-instance')
class LoadBalancingTargetInstance(QueryResourceManager):
    """    GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/targetInstances
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetInstances'
        enum_spec = ('aggregatedList', 'items.*.targetInstances[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            name, "description", "creationTimestamp", "zone", "natPolicy", "instance"]
        asset_type = "compute.googleapis.com/TargetInstance"
        urn_component = "target-instance"
        urn_zonal = True

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'zone': resource_info['zone'],
                'targetInstance': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-target-pool')
class LoadBalancingTargetPool(QueryResourceManager):
    """    GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/targetPools
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetPools'
        enum_spec = ('aggregatedList', 'items.*.targetPools[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            name, "description", "region",
            "failoverRatio", "sessionAffinity", "backupPool"
        ]
        asset_type = "compute.googleapis.com/TargetPool"
        urn_component = "target-pool"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'region': resource_info['zone'],
                'targetPool': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-forwarding-rule')
class LoadBalancingForwardingRule(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/addresses
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'forwardingRules'
        enum_spec = ('aggregatedList', 'items.*.forwardingRules[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "region", "IPAddress", "IPProtocol", "target",
            "loadBalancingScheme", "serviceName", "network"
        ]
        asset_type = "compute.googleapis.com/ForwardingRule"
        urn_component = "forwarding-rule"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'region': resource_info['region'],
                'forwardingRule': resource_info['resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-global-forwarding-rule')
class LoadBalancingGlobalForwardingRule(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/forwardingRules
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'globalForwardingRules'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "network",
            "networkTier", "loadBalancingScheme", "subnetwork", "allowGlobalAccess"
        ]
        asset_type = "compute.googleapis.com/GlobalForwardingRule"
        urn_component = "global-forwarding-rule"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'forwardingRule': resource_info['resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-global-address')
class LoadBalancingGlobalAddress(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/globalAddresses
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'globalAddresses'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "status", "creationTimestamp", "address", "region"
        ]
        asset_type = "compute.googleapis.com/GlobalAddress"
        urn_component = "global-address"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'address': resource_info['resourceName'].rsplit('/', 1)[-1]})


@resources.register('loadbalancer-target-https-proxy')
class LoadBalancerTargetHttpsProxy(ChildResourceManager):

    class resource_type(ChildTypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetHttpsProxies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = name = 'name'
        default_report_fields = [id]
        parent_spec = {
            'resource': 'loadbalancer-backend-service',
            'child_enum_params': [],
        }
        asset_type = "compute.googleapis.com/TargetHttpsProxy"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {
                    'backendService': resource_info['backendService'],
                    'notification': resource_info['notification_id']
                })


@resources.register('loadbalancer-backend-ssl-policy')
class LoadBalancerBackendSslPolicy(ChildResourceManager):
    """
    GC resource: https://cloud.google.com/compute/docs/reference/rest/v1/sslPolicies
    """
    class resource_type(ChildTypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'sslPolicies'
        enum_spec = ('list', 'items[]', None)
        id = name = 'name'
        default_report_fields = [id, 'profile', 'minTlsVersion']
        parent_spec = {
            'resource': 'loadbalancer-target-https-proxy',
        }
        asset_type = "compute.googleapis.com/SslPolicy"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {
                    'backendService': resource_info['backendService'],
                    'notification': resource_info['notification_id']
                })

    def _get_child_enum_args_list(self, parent_instance):
        ssl_policy_full_name = jmespath_search('sslPolicy', parent_instance)
        if ssl_policy_full_name:
            ssl_policy_name = re.match('.*/global/sslPolicies/(.*)', ssl_policy_full_name
                                       ).group(1)
            return [{'filter': 'name={}'.format(ssl_policy_name)}]
        return []


@resources.register('loadbalancer-ssl-policy')
class LoadBalancerSslPolicy(ChildResourceManager):
    """
    GC resource: https://cloud.google.com/compute/docs/reference/rest/v1/sslPolicies

    Unlike loadbalancer-ssl-policy, returns only policies that are tied to
    loadbalancer-target-https-proxy resources.
    """

    class resource_type(ChildTypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'sslPolicies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        get_requires_event = True
        default_report_fields = [
            name, "description", "sslPolicy", "urlMap"
        ]
        parent_spec = {
            'resource': 'loadbalancer-target-https-proxy',
        }
        asset_type = "compute.googleapis.com/SslPolicy"

        @staticmethod
        def get(client, event):
            self_link = jmespath_search('protoPayload.request.sslPolicy', event)
            parent_resource_name = jmespath_search('protoPayload.resourceName', event)
            project = re.match('.*projects/(.*?)/global/targetHttpsProxies/.*',
                               parent_resource_name).group(1)
            ssl_policy = {'project_id': project, 'parent_resource_name': parent_resource_name}
            if self_link:
                name = re.match('.*projects/.*?/global/sslPolicies/(.*)', self_link).group(1)
                ssl_policy.update(client.execute_command(
                    'get', {'project': project, 'sslPolicy': name}))
            return ssl_policy

    def _get_child_enum_args(self, parent_instance):
        child_enum_args = {}
        ssl_policy = parent_instance['sslPolicy'] if 'sslPolicy' in parent_instance else None
        if ssl_policy:
            ssl_policy_name = re.match('.*/global/sslPolicies/(.*)', ssl_policy).group(1)
        else:
            ssl_policy_name = 'GCP default'
        child_enum_args['filter'] = 'name = \"%s\"' % ssl_policy_name
        return child_enum_args

    def _get_parent_resource_info(self, child_instance):
        return {'project_id': child_instance['project_id'],
                'resourceName': child_instance['parent_resource_name']}
