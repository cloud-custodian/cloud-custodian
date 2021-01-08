# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, VpcFilter
from c7n.manager import resources
from c7n import tags
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema
from botocore.waiter import WaiterModel, create_waiter_with_client
from .aws import shape_validate


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
        cfn_type = 'AWS::EKS::Cluster'

    def augment(self, resources):
        resources = super(EKS, self).augment(resources)
        for r in resources:
            if 'tags' not in r:
                continue
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in r['tags'].items()]
        return resources


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
