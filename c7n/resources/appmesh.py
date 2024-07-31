"""
AppMesh Communications
"""
from c7n.manager import resources
from c7n.query import (
    ChildResourceManager,
    QueryResourceManager,
    TypeInfo,
    DescribeSource,
    ChildDescribeSource,
    ConfigSource,
)
from c7n.resources.aws import Arn
from c7n.tags import universal_augment
from c7n.filters import ListItemFilter
from c7n.utils import (
    local_session, type_schema
)


class DescribeMesh(DescribeSource):
    # override default describe augment to get tags
    def augment(self, resources):
        detailed_resources = super(DescribeMesh, self).augment(resources)
        tagged_resources = universal_augment(self.manager, detailed_resources)
        return tagged_resources


@resources.register('appmesh-mesh')
class AppmeshMesh(QueryResourceManager):
    source_mapping = {'describe': DescribeMesh,
                      'config': ConfigSource}

    # interior class that defines the aws metadata for resource
    class resource_type(TypeInfo):
        service = 'appmesh'

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html  # noqa
        cfn_type = 'AWS::AppMesh::Mesh'

        # https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html  # noqa
        config_type = 'AWS::AppMesh::Mesh'

        # id: Needs to be the field that contains the name of the mesh as that's
        # what the appmesh API's expect.
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-mesh.html   # noqa
        id = 'meshName'

        # This name value appears in the "report" command output.
        # example: custodian  report --format json  -s report-out mesh-policy.yml
        # See the meshName field here...
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-mesh.html   # noqa
        name = 'meshName'

        # Turn on collection of the tags for this resource
        universal_taggable = object()

        # enum_spec (list_meshes) function has arn as a top level field
        arn = "arn"

        enum_spec = ('list_meshes', 'meshes', None)

        # describe_mesh is the op to call
        # meshName is the field in the detail call args to populate
        # meshName is the field in the enum response to map into the call arg
        # mesh is the path in the response to pull out and merge into the list
        # response as the final product.
        detail_spec = ('describe_mesh', 'meshName', 'meshName', 'mesh')

        # refers to a field in the metadata response of the describe function
        # https://docs.aws.amazon.com/cli/latest/reference/appmesh/describe-mesh.html
        date = 'createdAt'


class DescribeVirtualGatewayDefinition(ChildDescribeSource):
    # This method is called in event mode and not pull mode.
    # Its purpose is to take a list of virtual gateway ARN's that the
    # framework has extracted from the events according to the policy yml file
    # and then call the describe function for the virtual gateway.
    def get_resources(self, arns, cache=True):
        # Split each arn into its parts and then return an object
        # that has the two names we need for the describe operation.
        # Mesh gw arn looks like : arn:aws:appmesh:eu-west-2:123456789012:mesh/Mesh7/virtualGateway/GW1  # noqa

        mesh_and_child_names = [
            {"meshName": parts[0], "virtualGatewayName": parts[2]} for parts in
            [Arn.parse(arn).resource.split('/') for arn in arns]
        ]

        return self._describe(mesh_and_child_names)

    # Called during event mode and pull mode, and it's function is to take id's
    # from some provided data and return the complete description of the resource.
    # The resources argument is a list of objects that contains at least
    # the fields meshName and virtualGatewayName.
    #
    # If we are in event mode then the resources will already be fully populated because
    # augment() is called with the fully populated output of get_resources() above.
    # But, if we are in pull mode then we only have some basic data returned from the
    # "parent" query enum function so we have to get the full details.
    def augment(self, resources):
        # Can detect if we are in event mode because the resource we get from
        # the event has the metadata field present. By contrast when we are in pull
        # mode then all we have is some skinny data from the parent's list function.
        event_mode = resources and "metadata" in resources[0]
        if not event_mode:
            resources = self._describe(resources)

        # fill in the tags
        return universal_augment(self.manager, resources)

    # takes a list of objects with fields meshName and virtualGatewayName
    def _describe(self, mesh_and_child_names):
        results = []
        client = local_session(self.manager.session_factory).client('appmesh')

        for names in mesh_and_child_names:
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/delete_virtual_gateway.html #noqa
            response = self.manager.retry(client.describe_virtual_gateway,
                                          meshName=names["meshName"],
                                          virtualGatewayName=names["virtualGatewayName"], )
            resource = response['virtualGateway']

            results.append(resource)
        return results


@resources.register('appmesh-virtualgateway', aliases=['appmesh-virtual-gateway'])
class AppmeshVirtualGateway(ChildResourceManager):
    source_mapping = {
        'describe': DescribeVirtualGatewayDefinition,
        'describe-child': DescribeVirtualGatewayDefinition,
        'config': ConfigSource,
    }

    # interior class that defines the aws metadata for resource
    # see c7n/query.py for documentation on fields.
    class resource_type(TypeInfo):
        # turn on support for cloundtrail for child resources
        supports_trailevents = True

        service = 'appmesh'

        # arn_type is used to manufacture arn's according to a recipe.
        # however in this case we don't need it because we've defined our
        # own get_arns function below.
        # arn_type = None

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html  # noqa
        # Optional - don't know what functionality relies on this.but this is the correct value.
        cfn_type = 'AWS::AppMesh::VirtualGateway'

        # locate the right value here ...
        # https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html  # noqa
        config_type = 'AWS::AppMesh::VirtualGateway'

        # turn on automatic collection of tags and tag filtering
        universal_taggable = object()

        # id: is not used by the resource collection process for this type because
        # this is a ChildResourceManager and instead it is the parent_spec function that drives
        # collection of "mesh id's".
        # However, it is still used by "report" operation so let's define it as something
        # even if not ideal.
        id = "metadata.arn"

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualgateway.html  # noqa
        # arn: not needed since we have defined our own "get_arns()" below
        arn = "metadata.arn"

        # This "name" value appears in the "report" command output.
        # example: custodian  report --format json  -s report-out mesh-policy.yml
        # see the virtualGatewayName field here...
        # https://docs.aws.amazon.com/cli/latest/reference/appmesh/describe-virtual-gateway.html # noqa
        name = 'virtualGatewayName'

        # refers to a field in the metadata response of the describe function
        # appears in the "report" operation
        # https://docs.aws.amazon.com/cli/latest/reference/appmesh/describe-virtual-gateway.html
        date = 'metadata.createdAt'

        # When we define a parent_spec then the parent_spec
        # provides the driving result set from which parent resource id's will be picked.
        # In this case the parent resource id is the meshName.
        # This is then iterated across and the enum_spec is called once for each parent 'id'.
        #
        # "appmesh-mesh" - identifies the parent data source (ie AppmeshMesh).
        # "meshName" - is the field from the parent spec result that will be pulled out and
        # used to drive the vgw enum_spec.
        parent_spec = ('appmesh-mesh', 'meshName', None)

        # enum_spec's list function is called once for each key (meshName) returned from
        # the parent_spec.
        # 'virtualGateways' - is path in the enum_spec response to locate the virtual
        # gateways for the given meshName.
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/list_virtual_gateways.html  # noqa
        enum_spec = (
            'list_virtual_gateways',
            'virtualGateways',
            None,
        )


class DescribeVirtualNodeDefinition(ChildDescribeSource):
    # This method is called in event mode and not pull mode.
    # Its purpose is to take a list of virtual gateway ARN's that the
    # framework has extracted from the events according to the policy yml file
    # and then call the describe function for the virtual node.
    def get_resources(self, arns, cache=True):
        # Split each arn into its parts and then return an object
        # that has the two names we need for the describe operation.
        # Mesh virtual node arn looks like : arn:aws:appmesh:eu-west-2:123456789012:mesh/Mesh7/virtualNode/VN1  # noqa

        mesh_and_child_names = [
            {"meshName": parts[0], "virtualNodeName": parts[2]} for parts in
            [Arn.parse(arn).resource.split('/') for arn in arns]
        ]

        return self._describe(mesh_and_child_names)

    # Called during event mode and pull mode, and it's function is to take id's
    # from some provided data and return the complete description of the resource.
    # The resources argument is a list of objects that contains at least
    # the fields meshName and virtualNodeName.
    #
    # If we are in event mode then the resources will already be fully populated because
    # augment() is called with the fully populated output of get_resources() above.
    # But, if we are in pull mode then we only have some basic data returned from the
    # "parent" query enum function so we have to get the full details.
    def augment(self, resources):
        # Can detect if we are in event mode because the resource we get from
        # the event has the metadata field present. By contrast when we are in pull
        # mode then all we have is some skinny data from the parent's list function.
        event_mode = resources and "metadata" in resources[0]
        if not event_mode:
            resources = self._describe(resources)

        # fill in the tags
        return universal_augment(self.manager, resources)

    # takes a list of objects with fields meshName and virtualGatewayName
    def _describe(self, mesh_and_child_names):
        results = []
        client = local_session(self.manager.session_factory).client('appmesh')

        for names in mesh_and_child_names:
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/delete_virtual_node.html #noqa
            response = self.manager.retry(client.describe_virtual_node,
                                          meshName=names["meshName"],
                                          virtualNodeName=names["virtualNodeName"], )
            resource = response['virtualNode']

            results.append(resource)
        return results


@resources.register('appmesh-virtualnode')
class AppmeshVirtualNode(ChildResourceManager):
    source_mapping = {
        'describe': DescribeVirtualNodeDefinition,
        'describe-child': DescribeVirtualNodeDefinition,
        'config': ConfigSource,
    }

    # interior class that defines the aws metadata for resource
    # see c7n/query.py for documentation on fields.
    class resource_type(TypeInfo):
        # turn on support for cloundtrail for child resources
        supports_trailevents = True

        service = 'appmesh'

        # arn_type is used to manufacture arn's according to a recipe.
        # however in this case we don't need it because we've defined our
        # own get_arns function below.
        # arn_type = None
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html  # noqa
        # Optional - don't know what functionality relies on this.but this is the correct value.
        cfn_type = 'AWS::AppMesh::VirtualNode'

        # locate the right value here ...
        # https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html  # noqa
        config_type = 'AWS::AppMesh::VirtualNode'

        # turn on automatic collection of tags and tag filtering
        universal_taggable = object()

        # id: is not used by the resource collection process for this type because
        # this is a ChildResourceManager and instead it is the parent_spec function that drives
        # collection of "mesh id's".
        # However, it is still used by "report" operation so let's define it as something
        # even if not ideal.
        id = "metadata.arn"

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualnode.html  # noqa
        # arn: not needed since we have defined our own "get_arns()" below
        arn = "metadata.arn"

        # This "name" value appears in the "report" command output.
        # example: custodian  report --format json  -s report-out mesh-policy.yml
        # see the virtualNodeName field here...
        # https://docs.aws.amazon.com/cli/latest/reference/appmesh/describe-virtual-node.html # noqa
        name = 'virtualNodeName'

        # refers to a field in the metadata response of the describe function
        # appears in the "report" operation
        # https://docs.aws.amazon.com/cli/latest/reference/appmesh/describe-virtual-node.html
        date = 'metadata.createdAt'

        # When we define a parent_spec then the parent_spec
        # provides the driving result set from which parent resource id's will be picked.
        # In this case the parent resource id is the meshName.
        # This is then iterated across and the enum_spec is called once for each parent 'id'.
        #
        # "appmesh-mesh" - identifies the parent data source (ie AppmeshMesh).
        # "meshName" - is the field from the parent spec result that will be pulled out and
        # used to drive the vgw enum_spec.
        parent_spec = ('appmesh-mesh', 'meshName', None)

        # enum_spec's list function is called once for each key (meshName) returned from
        # the parent_spec.
        # 'virtualNodes' - is path in the enum_spec response to locate the virtual
        # nodes for the given meshName.
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/list_virtual_nodes.html  # noqa
        enum_spec = (
            'list_virtual_nodes',
            'virtualNodes',
            None,
        )


@AppmeshMesh.filter_registry.register('service')
class VirtualService(ListItemFilter):

    """Filter on appmesh virtual services as List-Item Filters.

    :example:

    .. code-block:: yaml

        policies:
          - name: appmesh-virtual-service-policy
            resource: aws.appmesh-mesh
            filters:
              - type: service
                attrs:
                  - or :
                      - type: value
                        key: meshOwner
                        op: ne
                        value: resourceOwner
                        value_type: expr
                      - not :
                          - type: value
                            key: virtualServiceName
                            op : regex
                            value: '^.*.local$'
    """

    schema = type_schema(
        'service',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    annotation_key = "virtualServices"
    permissions = ('appmesh:DescribeVirtualService',)

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.data['key'] = self.annotation_key

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('appmesh')
        for mesh in resources:
            response = self.manager.retry(client.list_virtual_services,
                                          meshName=mesh["meshName"])

            mesh[self.annotation_key] = response.get(
                'virtualServices', [])

        return super().process(resources, event)


@AppmeshMesh.filter_registry.register('router')
class VirtualRouter(ListItemFilter):

    """Filter on appmesh virtual routers as List-Item Filters.

    :example:

    .. code-block:: yaml

        policies:
          - name: appmesh-router-policy
            resource: aws.appmesh-mesh
            filters:
              - type: router
                attrs:
                  - type: value
                    key: meshOwner
                    op: ne
                    value: resourceOwner
                    value_type: expr

    """

    schema = type_schema(
        'router',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    annotation_key = "virtualRouters"
    permissions = ('appmesh:DescribeVirtualRouter',)

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.data['key'] = self.annotation_key

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('appmesh')
        for mesh in resources:
            response = self.manager.retry(client.list_virtual_routers,
                                          meshName=mesh["meshName"])

            mesh[self.annotation_key] = response.get(
                'virtualRouters', [])

        return super().process(resources, event)


@AppmeshMesh.filter_registry.register('route')
class AppmeshRoute(ListItemFilter):

    """Filter on appmesh routes from virtual routers as List-Item Filters.

    :example:

    .. code-block:: yaml

        policies:
          - name: appmesh-route-policy
            resource: aws.appmesh-mesh
            filters:
              - type: route
                key: virtualRouters[].routes[]
                attrs:
                  - type: value
                    key: meshOwner
                    op: ne
                    value: resourceOwner
                    value_type: "expr"

    """

    schema = type_schema(
        'route',
        key={'type': 'string'},
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )
    permissions = ('appmesh:DescribeVirtualRouter',)

    def __init__(self, data, manager=None):
        super().__init__(data, manager)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('appmesh')

        for mesh in resources:
            virtual_routers = self.manager.retry(client.list_virtual_routers,
                                                meshName=mesh["meshName"])

            mesh["virtualRouters"] = virtual_routers.get("virtualRouters", [])

            for virtual_router in virtual_routers['virtualRouters']:
                response = self.manager.retry(client.list_routes,
                                              meshName=virtual_router["meshName"],
                                              virtualRouterName=virtual_router["virtualRouterName"])

                virtual_router["routes"] = response.get("routes", [])

        return super().process(resources, event)


@AppmeshVirtualGateway.filter_registry.register('gateway-route')
class AppmeshGatewayRoute(ListItemFilter):
    """Filter on appmesh gateway routes as List-Item Filters.

    :example:

    .. code-block:: yaml

        policies:
          - name: appmesh-gateway-route-policy
            resource: aws.appmesh-virtualgateway
            filters:
              - type: gateway-route
                attrs:
                  - type: value
                    key: meshOwner
                    op: ne
                    value: resourceOwner
                    value_type: expr

    """

    schema = type_schema(
        'gateway-route',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    annotation_key = "gatewayRoutes"
    permissions = ('appmesh:DescribeRoute',)

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.data['key'] = self.annotation_key

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('appmesh')

        for virtual_gateway in resources:
            response = self.manager.retry(client.list_gateway_routes,
                                          meshName=virtual_gateway["meshName"],
                                          virtualGatewayName=virtual_gateway["virtualGatewayName"])

            virtual_gateway[self.annotation_key] = response.get("gatewayRoutes", [])

        return super().process(resources, event)
