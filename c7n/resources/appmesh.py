"""
AppMesh Communications
"""
from c7n.manager import resources
from c7n.tags import universal_augment
from c7n.query import (
    ChildResourceManager,
    QueryResourceManager,
    TypeInfo,
    DescribeSource,
    ChildDescribeSource,
    ConfigSource,
)
from c7n.resources.aws import Arn
from c7n.utils import local_session


class DescribeMesh(DescribeSource):
    # override default describe augment to get tags
    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('appmesh-mesh')
class AppmeshMesh(QueryResourceManager):
    source_mapping = {'describe': DescribeMesh, 'config': ConfigSource}

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

        arn = "arn"

        enum_spec = ('list_meshes', 'meshes', None)

        detail_spec = ('describe_mesh', 'meshName', 'meshName', None)

        # refers to a field in the metadata response of the describe function
        # https://docs.aws.amazon.com/cli/latest/reference/appmesh/describe-mesh.html
        date = 'createdAt'


class DescribeGatewayDefinition(ChildDescribeSource):
    # this method appears to be used only when in event mode and not pull mode
    def get_resources(self, ids, cache=True):
        results = []
        client = local_session(self.manager.session_factory).client('appmesh')
        # ids for events should be arns
        for i in ids:
            # split mesh gw arn :
            # arn:aws:appmesh:eu-west-2:123456789012:mesh/Mesh7/virtualGateway/GW1  # noqa
            mesh_name, _, gw_name = Arn.parse(i).resource.split('/')
            results.append(
                self.manager.retry(
                    client.describe_virtual_gateway,
                    meshName=mesh_name,
                    virtualGatewayName=gw_name,
                )['virtualGateway']
            )
        return results

    def augment(self, resources):
        # on event modes the resource has already been fully fetched, just get tags
        if resources and "metadata" in resources[0]:
            return universal_augment(self.manager, resources)

        # on pull modes, we're enriching the result of enum_spec
        results = []
        client = local_session(self.manager.session_factory).client('appmesh')
        for gateway_info in resources:
            results.append(
                self.manager.retry(
                    client.describe_virtual_gateway,
                    meshName=gateway_info['meshName'],
                    virtualGatewayName=gateway_info['virtualGatewayName'],
                )['virtualGateway']
            )

        return universal_augment(self.manager, results)


@resources.register('appmesh-virtual-gateway')
class AppmeshVirtualGateway(ChildResourceManager):
    source_mapping = {
        'describe': DescribeGatewayDefinition,
        'describe-child': DescribeGatewayDefinition,
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

        # id: is not used by the resource collection process because this is a child function
        # and it is the parent_spec function that drives collection of "mesh id's".
        # However, it is still used by reporting.
        # The only unique field across all virtual gw resources is the ARN.
        id = "arn"

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualgateway.html  # noqa
        # arn: not needed since we have defined our own "get_arns()" below
        # arn = "arn"

        # This "name" value appears in the "report" command output.
        # example: custodian  report --format json  -s report-out mesh-policy.yml
        # see the virtualGatewayName field here...
        # https://docs.aws.amazon.com/cli/latest/reference/appmesh/describe-virtual-gateway.html # noqa
        name = 'virtualGatewayName'

        # refers to a field in the metadata response of the describe function
        # https://docs.aws.amazon.com/cli/latest/reference/appmesh/describe-virtual-gateway.html
        date = 'createdAt'

        # When we define a parent_spec then the parent_spec
        # provides the driving result set from which resource id's will be picked.
        # This is then iterated across and the enum_spec is called for each parent instance 'id'.
        # appmesh-mesh - is ref to another resource above that
        # provides the driving value for the enum_spec meshName - is
        # the field from the parent spec that will be pulled out and
        # used to drive the enum_spec.
        parent_spec = ('appmesh-mesh', 'meshName', None)

        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/list_virtual_gateways.html  # noqa
        # virtualGateways is path to collection to return from the list response
        enum_spec = (
            'list_virtual_gateways',
            'virtualGateways',
            None,
        )

    def get_arns(self, resources):
        return [r['metadata']['arn'] for r in resources]
