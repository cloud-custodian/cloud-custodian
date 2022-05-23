from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import universal_augment


@resources.register('lakeformation-resource')
class LakeFormation(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'lakeformation'
        enum_spec = ('list_resources', 'ResourceInfoList', None)
        arn = id = 'ResourceArn'
        name = 'name'
        cfn_type = "AWS::LakeFormation::Resource"
        universal_taggable = object()

    augment = universal_augment
