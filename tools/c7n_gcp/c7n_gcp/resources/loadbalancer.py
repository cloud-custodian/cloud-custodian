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


from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
import jmespath


@resources.register('loadbalancer-address')
class LoadBalancingAddress(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'addresses'
        enum_spec = ('aggregatedList', 'items.*.addresses[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'region': jmespath.search('resource.labels.location', event),
                        'address': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-url-map')
class LoadBalancingUrlMap(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'urlMaps'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'urlMap': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-target-tcp-proxy')
class LoadBalancingTargetTcpProxy(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetTcpProxies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'targetTcpProxy': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-target-ssl-proxy')
class LoadBalancingTargetSslProxy(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetSslProxies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'targetSslProxy': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-ssl-policy')
class LoadBalancingSslPolicy(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'sslPolicies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'sslPolicy': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-ssl-certificate')
class LoadBalancingSslCertificate(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'sslCertificates'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'sslCertificate': jmespath.search(
                            'resource.labels.ssl_certificate_name', event)}
            )


@resources.register('loadbalancer-target-https-proxy')
class LoadBalancingTargetHttpsProxy(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetHttpsProxies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'targetHttpsProxy': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-backend-bucket')
class LoadBalancingBackendBucket(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'backendBuckets'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'backendBucket': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-https-health-check')
class LoadBalancingHttpsHealthCheck(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'httpsHealthChecks'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'httpsHealthCheck': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-http-health-check')
class LoadBalancingHttpHealthCheck(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'httpHealthChecks'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'httpHealthCheck': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-health-check')
class LoadBalancingHealthCheck(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'healthChecks'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'healthCheck': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-target-http-proxy')
class LoadBalancingTargetHttpProxy(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetHttpProxies'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'targetHttpProxy': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-backend-service')
class LoadBalancingBackendService(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'backendServices'
        enum_spec = ('aggregatedList', 'items.*.backendServices[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'backendService': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-target-instance')
class LoadBalancingTargetInstance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetInstances'
        enum_spec = ('aggregatedList', 'items.*.targetInstances[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'zone': jmespath.search('resource.labels.zone', event),
                        'targetInstance': jmespath.search(
                            'protoPayload.resourceName',
                            event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-target-pool')
class LoadBalancingTargetPool(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'targetPools'
        enum_spec = ('aggregatedList', 'items.*.targetPools[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'region': jmespath.search('resource.labels.zone', event),
                        'targetPool': jmespath.search('protoPayload.resourceName',
                                                      event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-forwarding-rule')
class LoadBalancingForwardingRule(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'forwardingRules'
        enum_spec = ('aggregatedList', 'items.*.forwardingRules[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'region': jmespath.search('resource.labels.region', event),
                        'forwardingRule': jmespath.search('protoPayload.resourceName',
                                                          event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-global-forwarding-rule')
class LoadBalancingGlobalForwardingRule(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'globalForwardingRules'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'forwardingRule': jmespath.search('protoPayload.resourceName',
                                                          event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-global-address')
class LoadBalancingGlobalAddress(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'globalAddresses'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'address': jmespath.search('protoPayload.resourceName',
                                                   event).rsplit('/', 1)[-1]}
            )


@resources.register('loadbalancer-region-backend-service')
class LoadBalancingRegionBackendService(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'regionBackendServices'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {'project': jmespath.search('resource.labels.project_id', event),
                        'region': jmespath.search('resource.labels.location', event),
                        'backendService': jmespath.search('protoPayload.resourceName',
                                                          event).rsplit('/', 1)[-1]}
            )

    def get_resource_query(self):
        if 'query' in self.data and self.data.get('query')[0].__contains__('region'):
            return {'region': self.data.get('query')[0]['region']}
