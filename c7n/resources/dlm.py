# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import Tag, RemoveTag


@resources.register('dlm-policy')
class DLMPolicy(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'dlm'
        id = name = 'PolicyId'
        enum_spec = (
            'get_lifecycle_policies', 'Policies', None)
        detail_spec = ('get_lifecycle_policy', 'PolicyId', 'PolicyId', 'Policy')
        filter_name = 'PolicyIds'
        filter_type = 'list'
        arn = 'PolicyArn'
        arn_type = 'policy'
        cfn_type = 'AWS::DLM::LifecyclePolicy'
        # arn:aws:dlm:us-east-1:532725030595:policy/policy-0e23a047d0fdb7761

    def augment(self, resources):
        super().augment(resources)
        for r in resources:
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in r.get('Tags', {}).items()]
        return resources


@DLMPolicy.action_registry.register('tag')
class TagDLMPolicy(Tag):

    permissions = ('dlm:TagResource', )

    def process_resource_set(self, client, resource_set, tags):
        arns = self.manager.get_arns(resource_set)
        for arn in arns:
            client.tag_resource(
                ResourceArn=arn,
                Tags={t['Key']: t['Value'] for t in tags})


@DLMPolicy.action_registry.register('remove-tag')
class DLMPolicyRemoveTag(RemoveTag):

    permissions = ('dlm:UntagResource', )

    def process_resource_set(self, client, resource_set, tag_keys):
        arns = self.manager.get_arns(resource_set)
        for arn in arns:
            client.untag_resource(
                ResourceArn=arn,
                TagKeys=tag_keys
            )
