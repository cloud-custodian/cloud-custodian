"""
Service Discovery Communications
"""
from c7n.manager import resources
from c7n.query import (
    QueryResourceManager,
    TypeInfo,
    DescribeSource,
    ConfigSource,
)
from c7n.tags import universal_augment
from c7n.filters import ListItemFilter

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
