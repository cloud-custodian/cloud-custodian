"""
AppMesh Communications
"""
import logging

from c7n import query
from c7n.exceptions import PolicyExecutionError
from c7n.manager import resources
from c7n.query import ChildResourceManager, QueryResourceManager, TypeInfo, \
    ChildDescribeSource
from c7n.utils import (
    local_session)

#log = logging.getLogger('custodian.appmesh')
#logging.getLogger('botocore.client').setLevel(logging.DEBUG)
#logging.getLogger('botocore.endpoint').setLevel(logging.DEBUG)
#logging.getLogger('botocore.parsers').setLevel(logging.DEBUG)


@resources.register('appmesh-mesh')
class AppmeshMesh(QueryResourceManager):

    # interior class that defines the aws metadata for resource
    class resource_type(TypeInfo):
        service = 'appmesh'
        arn_type = "mesh"

        # field in response containing the identifier
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-mesh.html
        id = name = 'meshName'

        # this defines the boto3 call for the resource as well as JMESPATH
        # for accessing TL resources
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/list_meshes.html
        # enum_op - the aws api op
        # path - path to the field in the response that is the collection of result objects
        # extra_args - eg {'maxResults': 100}
        enum_spec = (
            'list_meshes', 'meshes', None
        )

        # detail_op = boto api call name
        # param_name = name of argument to boto api call
        # param_key = name of field in enum_spec response to drive this call
        # detail_path = path to pull out of the boto response and return as the detail result
        #               if not provided then whole response is included in results
        detail_spec = (
            'describe_mesh', 'meshName', 'meshName', None
        )

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualnode.html
        cfn_type = config_type = 'AWS::AppMesh::Mesh'


        # filter_name:
        # When fetching a single resource via enum_spec this
        # is technically optional, but effectively required
        # for serverless event policies else we have to
        # enumerate the population. This parameter names a parameter
        # to the boto call that can be used to narrow the results
        # filter_name = ...
        # filter_type = ...



@resources.register('appmesh-virtual-gateway')
class AppmeshVirtualGateway(ChildResourceManager):

    # interior class that defines the aws metadata for resource
    #### INSPIRED BY
    #   @resources.register('event-rule-target')
    #   class EventRuleTarget(ChildResourceManager):
    class resource_type(TypeInfo):

        # turn on support for cloundtrail
        supports_trailevents = True

        service = 'appmesh'
        arn_type = "virtualGateway"
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualgateway.html
        # probably wrong as the arn is a different field
        #OLD arn = "meshName"
        #arn = "metadata.arn"

        id = name = 'meshName'
        date = 'createdAt'

        # when we define a parent_spec then it uses the parent spec to provide the driving result set.
        # this is then iterated across and the enum_spec is called for each parent instance.
        # appmesh-mesh - is ref to another resource above that provides the driving value for the enum_spec
        # meshName - is the field from the parent spec that will be pulled out and used to drive the enum_spec.
        parent_spec = (
            'appmesh-mesh', 'meshName', None
        )

        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/list_virtual_gateways.html
        # virtualGateways is path to collection to return from the list response
        enum_spec = (
            'list_virtual_gateways', 'virtualGateways', None # {'limit': 100} #"'meshName' # , None
        )

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualgateway.html
        cfn_type = config_type = 'AWS::AppMesh::VirtualGateway'

    # copied from ECS Task
    @property
    def source_type(self):
        source = self.data.get('source', 'describe')
        if source in ('describe', 'describe-child'):
            source = 'describe-virtual-gateway'
        return source


    def get_resources(self, ids, cache=True, augment=True):
        return super(AppmeshVirtualGateway, self).get_resources(ids, cache, augment=False)


@query.sources.register('describe-virtual-gateway')
class DescribeGatewayDefinition(ChildDescribeSource):
    def __init__(self, manager):
        # based on ECSClusterResourceDescribeSource
        self.manager = manager
        self.query = query.ChildResourceQuery(
            self.manager.session_factory, self.manager)
        self.query.capture_parent_id = True

    # this method appears to be used only when in event mode and not pull mode
    def get_resources(self, ids, cache=True):

        cluster_resources = {}

        # ids
        for i in ids:
            # split mesh gw arn : arn:aws:appmesh:eu-west-2:659775036450:mesh/Mesh7/virtualGateway/GW1

            _, ident = i.rsplit(':', 1)
            parts = ident.split('/', 3)

            if len(parts) != 4:
                raise PolicyExecutionError(f"Mesh Virtual Gateway arn (4 parts) required but got ({len(parts)} parts) : " + i)

            meshName = parts[1]
            gwName = parts[3]

            cluster_resources.setdefault(meshName, []).append(gwName)

        results = []
        client = local_session(self.manager.session_factory).client('appmesh')

        for meshName, gwIds in cluster_resources.items():
            res = self.describe_virtual_gateways(client, meshName, gwIds)
            results.extend(res)

        return results

    # # this method appears to be used only when in pull mode and not event mode
    def augment(self, resources):
        results = []

        client = local_session(self.manager.session_factory).client('appmesh')

        for res in resources:
            meshName, data = res

            response = self.manager.retry(
                client.describe_virtual_gateway,
                meshName=meshName,
                virtualGatewayName=data["virtualGatewayName"]
            )

            r = response['virtualGateway']
            results.append(r)

        return results


    # from ecs ECSTaskDescribeSource process_cluster_resources
    def describe_virtual_gateways(self, client, meshName, gwIds):
        results = []
        for gw in gwIds:
            res = self.manager.retry(
                client.describe_virtual_gateway,
                meshName=meshName,
                virtualGatewayName=gw
                #include=['TAGS']
            )
            r = res['virtualGateway']
            results.append(r)

        return results





# NOT TESTED
# @resources.register('appmesh-virtual-node')
# class AppmeshVirtualNode(QueryResourceManager):
#
#     # interior class that defines the aws metadata for resource
#     class resource_type(TypeInfo):
#         service = 'appmesh'
#         arn_type = "virtualNode"
#         # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualnode.html
#         id = name = 'VirtualNodeName'
#         #date = 'CreatedTime'
#
#         # this defines the boto3 call for the resource as well as JMESPATH
#         # for accessing TL resources
#         # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/list_meshes.html
#         enum_spec = (
#             'list_meshes', 'meshes', None
#         )
#
#         #  /mnt/c/Users/johnl/work/cloudcustodian/github/cloud-custodian/c7n/query.py 737
#         #  detail_spec:
#         #     detail_op = boto api call name
#         #     param_name = name of argument to boto api call
#         #     param_key = name of field in enum_spec response to drive this call
#         #     detail_path = path to pull out of the boto response and return as the detail result
#         #
#         # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/list_virtual_nodes.html
#         detail_spec = (
#             'list_virtual_nodes', 'meshName', 'meshName', None
#         )
#
#         # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualnode.html
#         cfn_type = config_type = 'AWS::AppMesh::VirtualNode'


