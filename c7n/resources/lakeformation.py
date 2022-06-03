from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('lakeformation')
class LakeFormation(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'lakeformation'
        enum_spec = ('list_resources', 'ResourceInfoList', None)
        arn = id = 'ResourceArn'
        name = 'name'
        cfn_type = "AWS::LakeFormation::Resource"
        arn_type = 'Resource'
        universal_taggable = object()
