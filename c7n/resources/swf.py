# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.tags import Tag, RemoveTag, universal_augment


class DescribeSimpleWorkflow(DescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('swf')
class SimpleWorkflow(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'swf'
        arn_type = ''
        enum_spec = ('list_domains', 'domainInfos', {'registrationStatus': 'REGISTERED'})
        id = name = 'name'
        arn = 'arn'
        universal_taggable = object()
        permission_augment = ('swf:ListTagsForResource',)

    source_mapping = {
        'describe': DescribeSimpleWorkflow,
        'config': ConfigSource
    }


@SimpleWorkflow.action_registry.register('tag')
class TagSWF(Tag):
    """Tag a Simple Workflow resource with a key/value

    :example:

    .. code-block:: yaml

            policies:
              - name: swf-domain-tag-ownername
                resource: swf
                filters:
                  - "tag:OwnerName": absent
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
    """
    permissions = ('swf:TagResource',)

    def process_resource_set(self, client, resources, tags):
        tags_lower = []

        for t in tags:
            tags_lower.append({k.lower(): v for k, v in t.items()})

        for r in resources:
            try:
                client.tag_resource(resourceArn=r['arn'], tags=tags_lower)
            except client.exceptions.ResourceNotFound:
                continue


@SimpleWorkflow.action_registry.register('remove-tag')
class RemoveTagSWF(RemoveTag):
    """Remove tag from a Simple Workflow resource with a provided key

    :example:

    .. code-block:: yaml

            policies:
              - name: swf-domain-remove-tag
                resource: swf
                filters:
                  - "tag:OwnerName": present
                actions:
                  - type: remove-tag
                    tags: ["OwnerName"]
    """
    permissions = ('swf:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):
        for r in resources:
            try:
                client.untag_resource(resourceArn=r['arn'], tagKeys=tag_keys)
            except client.exceptions.ResourceNotFound:
                continue
