# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema, local_session
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


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
        asset_type = " compute.googleapis.com/TargetTcpProxy"

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
            "loadBalancerScheme", "serviceName",
        ]
        asset_type = "compute.googleapis.com/ForwardingRule"

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
            "networkTier", "loadBalancerScheme", "subnetwork", "allowGlobalAccess"
        ]
        asset_type = "compute.googleapis.com/GlobalForwardingRule"

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

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'address': resource_info['resourceName'].rsplit('/', 1)[-1]})
