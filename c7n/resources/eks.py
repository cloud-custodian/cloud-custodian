# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, VpcFilter
from c7n.manager import resources
from c7n import tags
from c7n.query import QueryResourceManager, ChildResourceManager, TypeInfo, DescribeSource
from c7n import query
from c7n.utils import local_session, type_schema
from botocore.waiter import WaiterModel, create_waiter_with_client
from .aws import shape_validate
from .ecs import ContainerConfigSource


@query.sources.register('describe-eks-nodegroup')
class NodeGroupDescribeSource(query.ChildDescribeSource):

    def get_query(self):
        query = super(NodeGroupDescribeSource, self).get_query()
        query.capture_parent_id = True
        return query

    def augment(self, resources):
        results = []
        with self.manager.executor_factory(
                max_workers=self.manager.max_workers) as w:
            client = local_session(self.manager.session_factory).client('eks')
            for clusterName, nodegroupName in resources:
                nodegroup = client.describe_nodegroup(
                        clusterName=clusterName,
                        nodegroupName=nodegroupName
                    )['nodegroup']
                if 'tags' in nodegroup:
                    nodegroup['Tags'] = [{'Key': k, 'Value': v} for k, v in nodegroup['tags'].items()]
                results.append(nodegroup)
        return results


@resources.register('nodegroup')
class NodeGroup(ChildResourceManager):

    chunk_size = 10

    class resource_type(TypeInfo):

        service = 'eks'
        arn = 'arn'
        arn_type = 'nodegroup'
        name = id = 'nodegroup-name'
        enum_spec = ('list_nodegroups', 'nodegroups', None)
        detail_spec = ('describe_nodegroup', 'nodegroupName', 'clusterName', None)
        parent_spec = ('eks', 'clusterName', None)
        permissions_enum = ('eks:DescribeNodegroup',)
        date = 'createdAt'

    source_mapping = {
        'describe-child': NodeGroupDescribeSource,
        'describe': NodeGroupDescribeSource,
    }


class EKSDescribeSource(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        for r in resources:
            if 'tags' not in r:
                continue
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in r['tags'].items()]
        return resources


class EKSConfigSource(ContainerConfigSource):
    mapped_keys = {'certificateAuthorityData': 'certificateAuthority'}


@resources.register('eks')
class EKS(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'eks'
        enum_spec = ('list_clusters', 'clusters', None)
        arn = 'arn'
        arn_type = 'cluster'
        detail_spec = ('describe_cluster', 'name', None, 'cluster')
        id = name = 'name'
        date = 'createdAt'
        config_type = cfn_type = 'AWS::EKS::Cluster'

    source_mapping = {
        'config': EKSConfigSource,
        'describe': EKSDescribeSource
    }


@EKS.filter_registry.register('subnet')
class EKSSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "resourcesVpcConfig.subnetIds[]"


@EKS.filter_registry.register('security-group')
class EKSSGFilter(SecurityGroupFilter):

    RelatedIdsExpression = "resourcesVpcConfig.securityGroupIds[]"


@EKS.filter_registry.register('vpc')
class EKSVpcFilter(VpcFilter):

    RelatedIdsExpression = 'resourcesVpcConfig.vpcId'


@EKS.action_registry.register('tag')
class EKSTag(tags.Tag):

    permissions = ('eks:TagResource',)

    def process_resource_set(self, client, resource_set, tags):
        for r in resource_set:
            try:
                self.manager.retry(
                    client.tag_resource,
                    resourceArn=r['arn'],
                    tags={t['Key']: t['Value'] for t in tags})
            except client.exceptions.ResourceNotFoundException:
                continue


EKS.filter_registry.register('marked-for-op', tags.TagActionFilter)
EKS.action_registry.register('mark-for-op', tags.TagDelayedAction)


@EKS.action_registry.register('remove-tag')
class EKSRemoveTag(tags.RemoveTag):

    permissions = ('eks:UntagResource',)

    def process_resource_set(self, client, resource_set, tags):
        for r in resource_set:
            try:
                self.manager.retry(
                    client.untag_resource,
                    resourceArn=r['arn'], tagKeys=tags)
            except client.exceptions.ResourceNotFoundException:
                continue


@EKS.action_registry.register('update-config')
class UpdateConfig(Action):

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'oneOf': [
            {'required': ['type', 'logging']},
            {'required': ['type', 'resourcesVpcConfig']},
            {'required': ['type', 'logging', 'resourcesVpcConfig']}],
        'properties': {
            'type': {'enum': ['update-config']},
            'logging': {'type': 'object'},
            'resourcesVpcConfig': {'type': 'object'}
        }
    }

    permissions = ('eks:UpdateClusterConfig',)
    shape = 'UpdateClusterConfigRequest'

    def validate(self):
        cfg = dict(self.data)
        cfg['name'] = 'validate'
        cfg.pop('type')
        return shape_validate(
            cfg, self.shape, self.manager.resource_type.service)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('eks')
        state_filtered = 0
        params = dict(self.data)
        params.pop('type')
        for r in resources:
            if r['status'] != 'ACTIVE':
                state_filtered += 1
                continue
            client.update_cluster_config(name=r['name'], **params)
        if state_filtered:
            self.log.warning(
                "Filtered %d of %d clusters due to state", state_filtered, len(resources))


@EKS.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('eks:DeleteCluster',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('eks')
        for r in resources:
            try:
                self.delete_associated(r, client)
                client.delete_cluster(name=r['name'])
            except client.exceptions.ResourceNotFoundException:
                continue

    def delete_associated(self, r, client):
        nodegroups = client.list_nodegroups(clusterName=r['name'])['nodegroups']
        fargate_profiles = client.list_fargate_profiles(
            clusterName=r['name'])['fargateProfileNames']
        waiters = []
        if nodegroups:
            for nodegroup in nodegroups:
                self.manager.retry(
                    client.delete_nodegroup, clusterName=r['name'], nodegroupName=nodegroup)
                # Nodegroup supports parallel delete so process in parallel, check these later on
                waiters.append({"clusterName": r['name'], "nodegroupName": nodegroup})
        if fargate_profiles:
            waiter = self.fargate_delete_waiter(client)
            for profile in fargate_profiles:
                self.manager.retry(
                    client.delete_fargate_profile,
                    clusterName=r['name'], fargateProfileName=profile)
                # Fargate profiles don't support parallel deletes so process serially
                waiter.wait(
                    clusterName=r['name'], fargateProfileName=profile)
        if waiters:
            waiter = client.get_waiter('nodegroup_deleted')
            for w in waiters:
                waiter.wait(**w)

    def fargate_delete_waiter(self, client):
        # Fargate profiles seem to delete faster @ roughly 2 minutes each so keeping defaults
        config = {
            'version': 2,
            'waiters': {
                "FargateProfileDeleted": {
                    'operation': 'DescribeFargateProfile',
                    'delay': 30,
                    'maxAttempts': 40,
                    'acceptors': [
                        {
                            "expected": "DELETE_FAILED",
                            "matcher": "path",
                            "state": "failure",
                            "argument": "fargateprofile.status"
                        },
                        {
                            "expected": "ResourceNotFoundException",
                            "matcher": "error",
                            "state": "success"
                        }
                    ]
                }
            }
        }
        return create_waiter_with_client("FargateProfileDeleted", WaiterModel(config), client)
