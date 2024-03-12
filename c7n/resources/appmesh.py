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

        # https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsappmesh.html#awsappmesh-resources-for-iam-policies   # noqa
        arn_type = "mesh"

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualnode.html  # noqa
        cfn_type = config_type = 'AWS::AppMesh::Mesh'

        # Field in response containing the identifier used in API's.
        # Therefore, this "id" field might be the arn field for some API's but
        # in the case of Appmesh" it needs to be the field that contains the
        # name of the mesh as that's what the appmesh API's expect.
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-mesh.html   # noqa
        id = name = 'meshName'

        # if a resource type is supported by resource group tagging
        # api setting this value get tag filters/actions
        universal_taggable = object()

        # arn : Defines a top level field in the resource definition that contains the ARN
        # value. This value is accessed used by the 'get_arns(..)' fn on the super-class
        # QueryResourceManager.
        #
        # If this value is not defined then 'get_arns' contains fallback logic.
        #
        # First fallback logic is to look at what's defined in the 'id' field.
        # If the value of the "id" field starts with "arn:" then that value is used as the arn.
        #
        # The last resort is an attempt at generating (guessing!) the ARN by assembling it from
        # various fields and runtime values based on a recipe defined in 'generate_arn()' on
        # the super-class QueryResourceManager.
        #
        # If you aren't going to define the "arn" field and can't rely on the "id" to be an
        # ARN then you might get lucky that "generate_arn" works for your resource type.
        # However, failing that then you should override "get_arns" function entirely and
        # implement your own logic.
        #
        # TESTING: Whatever approach you use (above) you REALLY SHOULD (!!!) include a unit
        # test that verifies that "get_arns" yields the right ARNs for your resources.
        # This test should be implemented as an additional assertion within the unit tests
        # you'll be already planning to create.
        # For example test_appmesh.py includes a call to "get_arns(resources)" and asserts
        # that the ARNs found by running the policy are the expected ones defined within
        # the test data JSON files in the "placebo" directory.
        arn = "arn"

        # enum_spec : Defines the boto3 call used to find at least basic
        # details all resources of the relevant type.  the data per
        # resource can be further enriched by a detail_spec function.
        # enum_spec is also used when we've received an event in which
        # case the results from enum_spec are filtered to include only
        # those in the event.
        #
        # If the enum function chosen allows a filter param to be
        # specified then the filtering can be done on the server
        # side. For instance, ASG uses "describe_auto_scaling_groups"
        # as the enum function and "AutoScalingGroupNames" as a filter
        # param to that function to limit the server side work.
        # However, it seems that most "cloud custodian" integrations
        # do not use this approach.  App mesh list_meshes doesn't
        # support filtering.  ...
        #
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/list_meshes.html  # noqa
        #
        # and so when an event is received then the enum function gets
        # called and the event id's get enriched.
        #
        # For example the specific identity found in an
        # event. However, if the enum op doesn't support filtering
        # then what will happen with events instead is a full list of
        # resources followed by client side filtering.
        #
        # params:
        #  enum_op - the aws api op
        #  path - JMESPATH path to the field in the response that is the collection of result
        #         objects
        #  extra_args - eg {'maxResults': 100}
        #
        enum_spec = ('list_meshes', 'meshes', None)

        # detail_spec: In many cases the enum_spec function is one of the
        # "describe_" style functions that return a full'ish spec that
        # is sufficient for the user detection, however in those cases
        # where the enum_spec is a "list_" style function then the
        # response to then enum call will tend to be lacking in detail and
        # might just be a list of id's. In these cases it is generally
        # necessary to define a "detail_spec" which can be used to
        # enrich the values provided by the enum_spec.
        #
        # detail_op = boto api call name
        # param_name = name of argument to boto api call
        # param_key = name of field in enum_spec response to drive this call
        # detail_path = path to pull out of the boto response and
        #               return as the detail result if not provided
        #               then whole response is included in results
        detail_spec = ('describe_mesh', 'meshName', 'meshName', None)


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
    # interior class that defines the aws metadata for resource
    # see c7n/query.py for documentation on fields.
    class resource_type(TypeInfo):
        # turn on support for cloundtrail for child resources
        supports_trailevents = True

        service = 'appmesh'

        # https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsappmesh.html#awsappmesh-resources-for-iam-policies  # noqa
        arn_type = "mesh"

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualgateway.html  # noqa
        cfn_type = config_type = 'AWS::AppMesh::VirtualGateway'

        # if a resource type is supported by resource group tagging
        # api setting this value get tag filters/actions
        universal_taggable = object()

        # id: Path to "id" field in the
        id = 'meshName'

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualgateway.html  # noqa
        arn = "metadata.arn"

        name = 'virtualGatewayName'
        date = 'createdAt'

        # When we define a parent_spec then it uses the parent_spec
        # to provide the driving result set.  This is then iterated
        # across and the enum_spec is called for each parent instance.
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

    source_mapping = {
        'describe': DescribeGatewayDefinition,
        'describe-child': DescribeGatewayDefinition,
        'config': ConfigSource,
    }

    def get_arns(self, resources):
        return [r['metadata']['arn'] for r in resources]
