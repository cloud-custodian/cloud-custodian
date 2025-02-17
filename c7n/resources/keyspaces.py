from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.actions import BaseAction
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import get_retry, local_session, type_schema


@resources.register('keyspace')
class Keyspace(QueryResourceManager):

    SYSTEM_KEYSPACES = [
        "system",
        "system_schema",
        "system_schema_mcs",
        "system_multiregion_info",
    ]

    class resource_type(TypeInfo):
        service = 'keyspaces'
        arn_type = 'keyspace'
        enum_spec = ('list_keyspaces', 'keyspaces', None)
        detail_spec = ('get_keyspace', 'keyspaceName', 'keyspaceName', None)
        id = 'keyspaceName'
        arn = 'resourceArn'
        name = 'keyspaceName'
        cfn_type = 'AWS::Cassandra::Keyspace'

    retry = staticmethod(get_retry(
        ("ConflictException", "InternalServerException",)
    ))

    def augment(self, resources):
        resources = [
            r for r in resources
            if r['keyspaceName'] not in self.SYSTEM_KEYSPACES
        ]
        client = local_session(self.session_factory).client(
            self.resource_type.service)

        def _augment(r):
            tags = self.retry(client.list_tags_for_resource,
                resourceArn=r['resourceArn'])['tags']
            r['Tags'] = [
                {'Key': t['key'], 'Value': t['value']}
                for t in tags
            ]
            return r
        resources = super().augment(resources)
        return list(map(_augment, resources))


Keyspace.filter_registry.register('marked-for-op', TagActionFilter)


@Keyspace.action_registry.register('tag')
class TagKeyspace(Tag):
    permissions = ('keyspaces:TagResource',)

    def process(self, resources):
        client = self.get_client()
        for r in resources:
            client.tag_resource(
                resourceArn=r['resourceArn'],
                tags=[{'key': k, 'value': v} for k, v in self.data.get('tags', {}).items()]
                )


@Keyspace.action_registry.register('mark-for-op')
class KeyspaceMark(TagDelayedAction):
    """Mark a Keyspace for future Custodian action

    :example:

    .. code-block:: yaml

            policies:
              - name: keyspace-mark-for-delete
                resource: keyspace
                filters:
                  - type: value
                    key: replicationStrategy
                    op: eq
                    value: SINGLE_REGION
                actions:
                  - type: mark-for-op
                    op: delete
                    days: 7
    """


@Keyspace.action_registry.register('remove-tag')
class RemoveTagKeyspace(RemoveTag):
    permissions = ('keyspaces:UntagResource',)

    def process(self, resources):
        client = self.get_client()
        tag_keys = self.data.get('tags', [])
        for r in resources:
            tags_to_remove = [
                {'key': t['Key'], 'value': t['Value']}
                for t in r['Tags'] if t['Key'] in tag_keys
            ]
            self.manager.retry(
                client.untag_resource,
                resourceArn=r['resourceArn'],
                tags=tags_to_remove
            )


@Keyspace.action_registry.register('update')
class UpdateKeyspace(BaseAction):
    schema = type_schema(
        'update',
        required=['replicationSpecification'],
        replicationSpecification={
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'required': ['replicationStrategy'],
                'replicationStrategy': {'type': {'enum': ['SINGLE_REGION', 'MULTI_REGION']}},
                'regionList': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                    }
                }
            }
        },
        clientSideTimestamps={
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'status': {'type': {'enum': ['ENABLED', 'DISABLED']}}
            }
        }
    )
    permissions = ('keyspaces:UpdateKeyspace',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)
        params = dict(self.data)
        params.pop('type')
        for r in resources:
            client.update_keyspace(
                keyspaceName=r['keyspaceName'],
                **params
            )


@Keyspace.action_registry.register('delete')
class DeleteKeyspace(BaseAction):
    schema = type_schema('delete')
    permissions = ('keyspaces:DeleteKeyspace',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)
        for r in resources:
            self.manager.retry(
                client.delete_keyspace,
                ignore_err_codes=('ResourceNotFoundException'),
                keyspaceName=r['keyspaceName'],
            )
