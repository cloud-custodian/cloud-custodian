# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session
from c7n import tags


@resources.register('swf')
class SimpleWorkflowDomain(QueryResourceManager):
    class resource_type(TypeInfo):
        service = arn_type = 'swf'
        enum_spec = ('list_domains', 'domainInfos', {'registrationStatus': 'REGISTERED'})
        id = name = 'name'
        universal_taggable = object()
        permission_augment = ('swf:ListTagsForResource',)

    def augment(self, rules):
        client = local_session(self.session_factory).client('swf')

        def _add_tags(r):
            r['Tags'] = client.list_tags_for_resource(
                resourceArn=r['arn']).get('tags', [])
            return r

        return list(map(_add_tags, rules))


@SimpleWorkflowDomain.action_registry.register('tag')
class Tag(tags.Tag):
    """Tag a Simple Workflow Domain with a key/value

    :example:

    .. code-block:: yaml

            policies:
              - name: swf-domain-tag-owner-tag
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
        for t in tags:
            if t.get('Key'):
                t['key'] = t['Key']
                del t['Key']
            if t.get('Value'):
                t['value'] = t['Value']
                del t['Value']

        for r in resources:
            try:
                client.tag_resource(
                    resourceArn=r['arn'],
                    tags=tags
                )
            except client.exceptions.ResourceNotFound:
                continue
