"""
AppMesh Communications
"""
from botocore.exceptions import ClientError

from c7n import query
from c7n.exceptions import PolicyExecutionError
from c7n.manager import resources
from c7n.query import ChildResourceManager, QueryResourceManager, TypeInfo, \
    ChildDescribeSource
from c7n.utils import (
    local_session)

@resources.register('appmesh-mesh')
class AppmeshMesh(QueryResourceManager):

    # interior class that defines the aws metadata for resource
    class resource_type(TypeInfo):
        service = 'appmesh'
        arn_type = "mesh"

        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-virtualnode.html
        cfn_type = config_type = 'AWS::AppMesh::Mesh'

        # field in response containing the identifier
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-appmesh-mesh.html
        id = name = 'meshName'

        # enum_spec defines the boto3 call used to find at least basic details all resources of the relevant type.
        # the data per resource can be further enriched by a detail_spec function.
        # enum_spec is also used when we've received an event in which case the results from enum_spec are filtered
        # to include only those in the event.
        #
        # If the enum function chosen allows a filter param to be specified then the filtering can be done on the server
        # side. For instance, ASG uses "describe_auto_scaling_groups" as the enum function and "AutoScalingGroupNames"
        # as a filter param to that function to limit the server side work.
        # However, it seems that most "cloud custodian" integrations do not use this approach.
        # App mesh list_meshes doesn't support filtering.  ...
        #     https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/appmesh/client/list_meshes.html
        # and so when an event is received then the enum function gets called and the event id's get enriched.

        # for example the specific identity found in an event. However, if the enum op doesn't support filtering
        # then what will happen with events instead is a full list of resources followed by client side filtering.
        # params:
        #  enum_op - the aws api op
        #  path - JMESPATH path to the field in the response that is the collection of result objects
        #  extra_args - eg {'maxResults': 100}
        #
        enum_spec = (
            'list_meshes', 'meshes', None
        )

        # In many cases the enum_spec function is one of the "describe_" style functions that return a
        # full'ish spec that is sufficient for the user detection, however in those cases where the enum_spec
        # is a "list_" style funtion then the response to then enum call will be lacking in detail and might just be
        # a list of id's. In these cases it is generally necessary to define a "detail_spec" which can be used to
        # enrich the values provided by the enum_spec.

        # detail_op = boto api call name
        # param_name = name of argument to boto api call
        # param_key = name of field in enum_spec response to drive this call
        # detail_path = path to pull out of the boto response and return as the detail result
        #               if not provided then whole response is included in results
        detail_spec = (
            'describe_mesh', 'meshName', 'meshName', None
        )

    # This function gets called with the id's retrieved from the event and is expected to return the
    # enriched resource definition.
    #
    # Explanation of logic:
    # The default impl on the superclass calls the enum_spec function, however for many resource types
    # this is useless since the enum function provides little specification and often everything the enum
    # function provides is also on the detail_spec function.
    # So where we're going to have to have a detail_spec and where the enum_spec is redundant then why
    # call the enum spec function at all?
    # This is a small speed / cost saving as it reduces the number of AWS API calls made for each event.
    # So, in the the case of the current resource we will simply skip the enum call entirely.
    #
    # TODO: Propose an improvement where we allow skipping of the enum_spec call self.source.get_resources(ids)
    def get_resources(self, ids, cache=True, augment=True):
        if not ids:
            return []
        if cache:
            resources = self._get_cached_resources(ids)
            if resources is not None:
                return resources
        try:
            # default impl calls the enum function here - but we're not going to do that
            # resources = self.source.get_resources(ids)

            # do the augment by mocking up a fake resource that has the field name (param_key)
            # specified by the describe_spec
            resources = [{"meshName": m} for m in ids]
            return self.augment(resources)
        except ClientError as e:
            self.log.warning("event ids not resolved: %s error:%s" % (ids, e))
            return []


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

        # when we define a parent_spec then it uses the parent sNpec to provide the driving result set.
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
        self.query = query.ChildResourceQuery(self.manager.session_factory, self.manager)
        self.query.capture_parent_id = True

    # this method appears to be used only when in event mode and not pull mode
    def get_resources(self, ids, cache=True):

        name_and_gw = {}

        # ids
        for i in ids:
            # split mesh gw arn : arn:aws:appmesh:eu-west-2:659775036450:mesh/Mesh7/virtualGateway/GW1

            _, ident = i.rsplit(':', 1)
            parts = ident.split('/', 3)

            if len(parts) != 4:
                raise PolicyExecutionError(f"Mesh Virtual Gateway arn (4 parts) required but got ({len(parts)} parts) : " + i)

            meshName = parts[1]
            gwName = parts[3]

            name_and_gw.setdefault(meshName, []).append(gwName)

        results = []
        client = local_session(self.manager.session_factory).client('appmesh')

        for meshName, gwIds in name_and_gw.items():
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


