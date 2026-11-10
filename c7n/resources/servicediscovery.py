"""
Service Discovery Communications
"""
from c7n.actions import Action
from c7n.manager import resources
from c7n.query import (
    QueryResourceManager,
    TypeInfo,
    DescribeSource,
    DescribeWithResourceTags,
    ConfigSource,
)
from c7n.tags import universal_augment
from c7n.filters import ListItemFilter
from c7n.filters.vpc import VpcFilter

from c7n.utils import (
    local_session, type_schema
)


class DescribeServiceDiscoveryNamespace(DescribeSource):
    # override default describe augment to get tags
    def augment(self, resources):
        detailed_resources = super().augment(resources)
        tagged_resources = universal_augment(self.manager, detailed_resources)
        return tagged_resources


@resources.register('servicediscovery-namespace')
class ServiceDiscoveryNamespace(QueryResourceManager):

    source_mapping = {'describe': DescribeServiceDiscoveryNamespace,
                      'config': ConfigSource}

    # interior class that defines the aws metadata for resource
    class resource_type(TypeInfo):
        service = 'servicediscovery'

        # id: Needs to be the field that contains the name of the service as that's
        # what the service discovery API's expect.
        id = 'Name'

        # This name value appears in the "report" command output.
        # example:
        # custodian  report --format json  -s report-out service-discovery-namespace-policy.yml
        name = 'Name'

        # Turn on collection of the tags for this resource
        universal_taggable = object()

        # enum_spec (list_namespaces) function has arn as a top level field
        arn = "Arn"

        enum_spec = ('list_namespaces', 'Namespaces', None)

        # get_namespace is the op to call
        # Id is the name of the parementer field in the detail call args to populate
        # Id is the key which is present in the enum response to map into the call arg
        # Namespace is the path in the response to pull out and merge into the list
        # response as the final product.
        detail_spec = ('get_namespace', 'Id', 'Id', 'Namespace')

        # refers to a field in the metadata response of the describe function
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/servicediscovery/client/get_namespace.html
        date = 'CreateDate'


@ServiceDiscoveryNamespace.filter_registry.register('service-instance')
class SdNamespaceInstance(ListItemFilter):

    """Filter on service discovery instances in the namespaces as List-Item Filters.

    :example:

    .. code-block:: yaml

        policies:
          - name: servicediscovery-instance-policy
            resource: servicediscovery-namespace
            filters:
              - type: service-instance
                key: Services[].Instances[],
                attrs:
                  - or:
                      - Attributes.AWS_EC2_INSTANCE_ID: present

    """

    schema = type_schema(
        'service-instance',
        key={'type': 'string'},
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    permissions = ('servicediscovery:GetInstance',)

    def __init__(self, data, manager=None):
        super().__init__(data, manager)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('servicediscovery')
        for namespace in resources:
            namespace_services = self.manager.retry(client.list_services,
                                                    Filters=[{'Name': 'NAMESPACE_ID',
                                                              'Values': [namespace['Id']],
                                                              'Condition': 'EQ'
                                                              }])

            namespace["Services"] = namespace_services.get("Services", [])
            for service in namespace_services['Services']:
                response = self.manager.retry(client.list_instances,
                                              ServiceId=service["Id"])
                service["Instances"] = response.get("Instances", [])

        return super().process(resources, event)


@ServiceDiscoveryNamespace.filter_registry.register('vpc')
class NamespaceVpcFilter(VpcFilter):
    """Filter private DNS namespaces by the VPCs associated with their hosted zone.

    Only ``DNS_PRIVATE`` namespaces are evaluated.

    :example:

    .. code-block:: yaml

        policies:
          - name: servicediscovery-namespace-unapproved-vpc
            resource: aws.servicediscovery-namespace
            filters:
              - type: vpc
                key: VpcId
                op: not-in
                value: [vpc-0123456789abcdef0]
    """

    RelatedIdsExpression = '"c7n:HostedZoneVpcs"[]'
    vpc_annotation_key = 'c7n:HostedZoneVpcs'

    def get_permissions(self):
        return super().get_permissions() + ['route53:GetHostedZone']

    def process(self, resources, event=None):
        resources = [r for r in resources if r.get('Type') == 'DNS_PRIVATE']
        client = local_session(self.manager.session_factory).client('route53')
        for r in resources:
            if self.vpc_annotation_key in r:
                continue
            zone = self.manager.retry(
                client.get_hosted_zone, Id=r['Properties']['DnsProperties']['HostedZoneId'])
            r[self.vpc_annotation_key] = [v['VPCId'] for v in zone.get('VPCs', [])]
        return super().process(resources, event)


@ServiceDiscoveryNamespace.action_registry.register('delete')
class DeleteNamespace(Action):
    """Delete a namespace.

    AWS rejects the request while the namespace still contains services.

    :example:

    .. code-block:: yaml

        policies:
          - name: servicediscovery-delete-public-namespace
            resource: aws.servicediscovery-namespace
            filters:
              - Type: DNS_PUBLIC
            actions:
              - delete
    """

    schema = type_schema('delete')
    permissions = ('servicediscovery:DeleteNamespace',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('servicediscovery')
        for r in resources:
            self.manager.retry(
                client.delete_namespace, Id=r['Id'], ignore_err_codes=('NamespaceNotFound',))


@resources.register('servicediscovery-service')
class ServiceDiscoveryService(QueryResourceManager):
    """AWS Cloud Map service.

    :example:

    .. code-block:: yaml

        policies:
          - name: servicediscovery-service-http-health-check
            resource: aws.servicediscovery-service
            filters:
              - HealthCheckConfig.Type: HTTP
    """

    source_mapping = {'describe': DescribeWithResourceTags}

    class resource_type(TypeInfo):
        service = 'servicediscovery'
        enum_spec = ('list_services', 'Services', None)
        detail_spec = ('get_service', 'Id', 'Id', 'Service')
        id = 'Id'
        name = 'Name'
        arn = 'Arn'
        date = 'CreateDate'
        cfn_type = 'AWS::ServiceDiscovery::Service'
        universal_taggable = object()


@ServiceDiscoveryService.filter_registry.register('instance')
class ServiceInstanceFilter(ListItemFilter):
    """Filter services on the instances registered to them.

    :example:

    .. code-block:: yaml

        policies:
          - name: servicediscovery-service-public-instance-ip
            resource: aws.servicediscovery-service
            filters:
              - type: instance
                attrs:
                  - type: value
                    key: Attributes.AWS_INSTANCE_IPV4
                    op: not-in
                    value_type: cidr
                    value: ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    """

    schema = type_schema(
        'instance',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'})

    annotation_key = 'c7n:Instances'
    permissions = ('servicediscovery:ListInstances',)

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        data['key'] = f'"{self.annotation_key}"'

    def get_item_values(self, service):
        if self.annotation_key in service:
            return service[self.annotation_key]
        client = local_session(self.manager.session_factory).client('servicediscovery')
        instances = self.manager.retry(
            client.get_paginator('list_instances').paginate,
            ServiceId=service['Id']
        ).build_full_result().get('Instances', [])
        service[self.annotation_key] = instances
        return instances


@ServiceDiscoveryService.action_registry.register('delete')
class DeleteService(Action):
    """Delete a service.

    AWS rejects the request while the service still has registered instances.

    :example:

    .. code-block:: yaml

        policies:
          - name: servicediscovery-delete-empty-service
            resource: aws.servicediscovery-service
            filters:
              - InstanceCount: 0
            actions:
              - delete
    """

    schema = type_schema('delete')
    permissions = ('servicediscovery:DeleteService',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('servicediscovery')
        for r in resources:
            self.manager.retry(
                client.delete_service, Id=r['Id'], ignore_err_codes=('ServiceNotFound',))
