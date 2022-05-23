from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('lakeformation-resource')
class LakeFormation(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'lakeformation'
        enum_spec = ('list_resources', 'ResourceInfoList', None)
        id = 'ResourceArn'
        name = 'name'
        cfn_type = "AWS::LakeFormation::Resource"
        arn = False
