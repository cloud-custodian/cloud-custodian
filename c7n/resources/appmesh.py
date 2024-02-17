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
from c7n.utils import local_session


class DescribeMesh(DescribeSource):
    # override default describe augment to get tags
    def augment(self, resources):
        return universal_augment(self.manager, resources)


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

        arn = "arn"

        enum_spec = ('list_meshes', 'meshes', None)

        detail_spec = ('describe_mesh', 'meshName', 'meshName', None)

        # refers to a field in the metadata response of the describe function
        # https://docs.aws.amazon.com/cli/latest/reference/appmesh/describe-mesh.html
        date = 'createdAt'


class DescribeGatewayDefinition(ChildDescribeSource):
    # This method is called in event mode and not pull mode.
    # Its purpose is to take a list of virtual gateway ARN's that the
    # framework has extracted from the events according to the policy yml file
    # and then call the describe function for the virtual gateway.
    def get_resources(self, arns, cache=True):
        # Split each arn into its parts and then return an object
        # that has the two names we need for the describe operation.
        # Mesh gw arn looks like : arn:aws:appmesh:eu-west-2:123456789012:mesh/Mesh7/virtualGateway/GW1  # noqa

        mesh_and_gw_names = [
            {"meshName": parts[0], "virtualGatewayName": parts[2]} for parts in
            [Arn.parse(arn).resource.split('/') for arn in arns]
        ]

        return  self._describe(mesh_and_gw_names)

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
    def _describe(self, mesh_and_gw_names):
        results = []
        client = local_session(self.manager.session_factory).client('appmesh')

        for names in mesh_and_gw_names:
            results.append(
                # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/delete_virtual_gateway.html #noqa
                self.manager.retry(
                    client.describe_virtual_gateway,
                    meshName=names["meshName"],
                    virtualGatewayName=names["virtualGatewayName"],
                )['virtualGateway']
            )
        return results


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
        # However, it is still used by reporting so let's define it.
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

    # Purpose is to extract the ARN from the given resource description..
    # The location of the ARN in the VGW resource is not at the top level
    # so we need to override the function that does the extraction.
    # If the arn had been at the top level of the data structure then it
    # would have been enough to define the "arn" config field in the Typeinfo class.
    # But at present we can't put a path line "metadata.arn" into
    # that config field, and the authors tell me that allowing that would
    # be too expensive. So we'll just DIY.
    def get_arns(self, resources):
        return [r['metadata']['arn'] for r in resources]
