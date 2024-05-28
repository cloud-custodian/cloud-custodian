from c7n.manager import resources
from c7n.actions import Action
from c7n.filters.kms import KmsRelatedFilter
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema
from c7n.tags import (
    TagDelayedAction,
    TagActionFilter,
    Tag as TagAction,
    RemoveTag as RemoveTagAction
)
from c7n.filters.backup import ConsecutiveAwsBackupsFilter


class DescribeTimestream(DescribeSource):
    def augment(self, resources):
        for r in resources:
            client = local_session(self.manager.session_factory).client('timestream-write')
            r['Tags'] = client.list_tags_for_resource(ResourceARN=r['Arn'])['Tags']
        return resources


@resources.register('timestream-database')
class TimestreamDatabase(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'timestream-write'
        arn_type = ''
        name = 'DatabaseName'
        id = arn = 'Arn'
        enum_spec = ('list_databases', 'Databases', {})
        permission_prefix = 'timestream'
        permissions = ('timestream:ListDatabases', )
        permissions_augment = ("timestream:ListTagsForResource",)
    source_mapping = {
        'describe': DescribeTimestream,
    }


@resources.register('timestream-table')
class TimestreamTable(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'timestream-write'
        arn_type = ''
        name = 'TableName'
        id = arn = 'Arn'
        enum_spec = ('list_tables', 'Tables', {})
        permission_prefix = 'timestream'
        permissions = ('timestream:ListTables', )

    source_mapping = {
        'describe': DescribeTimestream,
    }


@TimestreamDatabase.action_registry.register('tag')
@TimestreamTable.action_registry.register('tag')
class TimestreamTag(TagAction):

    permissions = ('timestream:TagResource', )

    def process_resource_set(self, client, resource_set, tags):
        for r in resource_set:
            client.tag_resource(ResourceARN=r['Arn'], Tags=tags)


@TimestreamDatabase.action_registry.register('remove-tag')
@TimestreamTable.action_registry.register('remove-tag')
class TimestreamRemoveTag(RemoveTagAction):

    permissions = ('timestream:UntagResource', )

    def process_resource_set(self, client, resource_set, tag_keys):
        for r in resource_set:
            client.untag_resource(ResourceARN=r['Arn'], TagKeys=tag_keys)


TimestreamDatabase.action_registry.register('mark-for-op', TagDelayedAction)
TimestreamTable.action_registry.register('mark-for-op', TagDelayedAction)

TimestreamDatabase.filter_registry.register('marked-for-op', TagActionFilter)
TimestreamTable.filter_registry.register('marked-for-op', TagActionFilter)


@TimestreamTable.action_registry.register('delete')
class TimestreamTableDelete(Action):
    """
    Deletes a timestream table
    """

    schema = type_schema('delete')
    permissions = ('timestream:DeleteTable', )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('timestream-write')
        for r in resources:
            try:
                client.delete_table(
                    DatabaseName=r['DatabaseName'],
                    TableName=r['TableName']
                )
            except client.exceptions.ResourceNotFoundException:
                continue


@TimestreamDatabase.action_registry.register('delete')
class TimestreamDatabaseDelete(Action):
    """
    Deletes a timestream database
    """

    schema = type_schema('delete', force={'type': 'boolean', 'default': False})
    permissions = (
        'timestream:DeleteDatabase',
        'timestream:ListTables', 'timestream:DeleteTable', )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('timestream-write')
        for r in resources:
            try:
                client.delete_database(
                    DatabaseName=r['DatabaseName'],
                )
            except client.exceptions.ResourceNotFoundException:
                continue
            except client.exceptions.ValidationException:
                if not self.data.get('force', False):
                    self.log.error(
                        f'Unable to delete database:{r["DatabaseName"]}, '
                        'tables must be deleted first')
                    continue
                tables = client.list_tables(DatabaseName=r['DatabaseName'])['Tables']
                TimestreamTableDelete(
                    data={'type': 'delete'},
                    manager=self.manager,
                    log_dir=self.log_dir
                ).process(tables)
                client.delete_database(
                    DatabaseName=r['DatabaseName'],
                )


TimestreamTable.filter_registry.register('consecutive-aws-backups', ConsecutiveAwsBackupsFilter)


@TimestreamDatabase.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'KmsKeyId'
