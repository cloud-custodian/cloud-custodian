# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import c7n.filters.vpc as net_filters
from c7n.actions import Action
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, VpcFilter
from c7n.manager import resources
from c7n.resources.aws import shape_schema
from c7n import tags, query
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, \
    ChildResourceManager, ChildDescribeSource
from c7n.utils import local_session, type_schema, get_retry
from botocore.waiter import WaiterModel, create_waiter_with_client
from .aws import shape_validate
from .ecs import ContainerConfigSource
from c7n.filters.kms import KmsRelatedFilter


@query.sources.register('describe-eks-nodegroup')
class NodeGroupDescribeSource(ChildDescribeSource):

    def get_query(self):
        return super().get_query(capture_parent_id=True)

    def augment(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('eks')
        for cluster_name, nodegroup_name in resources:
            nodegroup = client.describe_nodegroup(
                clusterName=cluster_name,
                nodegroupName=nodegroup_name)['nodegroup']
            if 'tags' in nodegroup:
                nodegroup['Tags'] = [{'Key': k, 'Value': v} for k, v in nodegroup['tags'].items()]
            results.append(nodegroup)
        return results


@resources.register('eks-nodegroup')
class NodeGroup(ChildResourceManager):

    class resource_type(TypeInfo):

        service = 'eks'
        arn = 'nodegroupArn'
        arn_type = 'nodegroup'
        id = 'nodegroupArn'
        name = 'nodegroupName'
        enum_spec = ('list_nodegroups', 'nodegroups', None)
        parent_spec = ('eks', 'clusterName', None)
        permissions_enum = ('eks:DescribeNodegroup',)
        date = 'createdAt'

    source_mapping = {
        'describe-child': NodeGroupDescribeSource,
        'describe': NodeGroupDescribeSource,
    }


@NodeGroup.action_registry.register('delete')
class DeleteNodeGroup(Action):
    """Delete node group(s)."""

    schema = type_schema('delete')
    permissions = ('eks:DeleteNodegroup',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('eks')
        retry = get_retry(('Throttling',))
        for r in resources:
            try:
                retry(client.delete_nodegroup,
                      clusterName=r['clusterName'],
                      nodegroupName=r['nodegroupName'])
            except client.exceptions.ResourceNotFoundException:
                continue


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


EKS.filter_registry.register('network-location', net_filters.NetworkLocation)


@EKS.filter_registry.register('vpc')
class EKSVpcFilter(VpcFilter):

    RelatedIdsExpression = 'resourcesVpcConfig.vpcId'


@EKS.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'encryptionConfig[].provider.keyArn'


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

    schema = type_schema('update-config',
                **shape_schema(
                    'eks', 'UpdateClusterConfigRequest', drop_fields=('name'))
            )

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


@EKS.action_registry.register('associate-encryption-config')
class AssociateEncryptionConfig(Action):
    """
    Action that adds an encryption configuration to an EKS cluster.

    :example:

    This policy will find all EKS clusters that do not have Secrets encryption set and
    associate encryption config with the specified keyArn.

    .. code-block:: yaml

        policies:
          - name: associate-encryption-config
            resource: aws.eks
            filters:
              - type: value
                key: encryptionConfig[].provider.keyArn
                value: absent
            actions:
              - type: associate-encryption-config
                encryptionConfig:
                  - provider:
                      keyArn: alias/eks
                    resources:
                      - secrets
    """
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['associate-encryption-config']},
            'encryptionConfig': {
                'type': 'array',
                'properties': {
                    'type': 'object',
                    'properties': {
                        'provider': {
                            'type': 'object',
                            'properties': {
                                'keyArn': {'type': 'string'}
                            }
                        },
                        'resources': {
                            'type': 'array',
                            'properties': {
                                'enum': 'secrets'
                            }
                        }
                    }
                }
            }
        }
    }

    permissions = ('eks:AssociateEncryptionConfig', 'kms:DescribeKey',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('eks')
        error = None
        params = dict(self.data)
        params.pop('type')
        # associate_encryption_config does not accept kms key aliases, if provided
        # with an alias find the key arn with kms:DescribeKey first.
        key_arn = params['encryptionConfig'][0]['provider']['keyArn']
        if 'alias' in key_arn:
            try:
                kms_client = local_session(self.manager.session_factory).client('kms')
                _key_arn = kms_client.describe_key(KeyId=key_arn)['KeyMetadata']['Arn']
                params['encryptionConfig'][0]['provider']['keyArn'] = _key_arn
            except kms_client.exceptions.NotFoundException as e:
                self.log.error(
                    "The following error was received for kms:DescribeKey: "
                    f"{e.response['Error']['Message']}"
                )
                raise e
        for r in self.filter_resources(resources, 'status', ('ACTIVE',)):
            try:
                client.associate_encryption_config(
                    clusterName=r['name'],
                    encryptionConfig=params['encryptionConfig']
                )
            except client.exceptions.InvalidParameterException as e:
                error = e
                self.log.error(
                    "The following error was received for cluster "
                    f"{r['name']}: {e.response['Error']['Message']}"
                )
                continue
        if error:
            raise error


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
