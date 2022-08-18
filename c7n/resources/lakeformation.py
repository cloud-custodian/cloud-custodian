from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.actions import BaseAction
from c7n.utils import local_session, type_schema


@resources.register('datalake-location')
class LakeFormationRegisteredLocation(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'lakeformation'
        enum_spec = ('list_resources', 'ResourceInfoList', None)
        arn = id = 'ResourceArn'
        name = ''
        cfn_type = "AWS::LakeFormation::Resource"
        arn_type = ''


@LakeFormationRegisteredLocation.action_registry.register('deregister')
class DeleteRegisteredLocation(BaseAction):
    schema = type_schema('deregister')
    permissions = ('lakeformation:DeregisterResource',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('lakeformation')
        for r in resources:
            try:
                self.manager.retry(client.deregister_resource, ResourceArn=r['ResourceArn'])
            except client.exceptions.InvalidInputException:
                continue
