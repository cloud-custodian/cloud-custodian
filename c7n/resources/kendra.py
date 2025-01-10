from c7n.actions import Action
from c7n.filters.kms import KmsRelatedFilter
from c7n.manager import resources
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema


class DescribeIndex(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('kendra')
class KendraIndex(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'kendra'
        arn_type = 'index'
        enum_spec = ('list_indices', 'IndexConfigurationSummaryItems', None)
        detail_spec = (
            'describe_index', 'Id', 'Id', None)
        id = 'Id'
        name = 'Name'
        date = 'UpdatedAt'
        universal_taggable = object()
        cfn_type = 'AWS::Kendra::Index'

    source_mapping = {
        'describe': DescribeIndex,
    }


@KendraIndex.filter_registry.register('kms-key')
class IndexKmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'ServerSideEncryptionConfiguration.KmsKeyId'


@KendraIndex.action_registry.register('delete')
class IndexDelete(Action):

    schema = type_schema('delete')
    permissions = ("kendra:DeleteIndex",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kendra')
        for r in resources:
            self.manager.retry(client.delete_index, Id=r['Id'])
