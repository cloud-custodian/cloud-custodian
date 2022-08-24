from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.actions import BaseAction
from c7n.utils import local_session, type_schema
from .aws import Arn
from c7n.filters import Filter, ValueFilter


@resources.register('datalake-location')
class LakeFormationRegisteredLocation(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'lakeformation'
        enum_spec = ('list_resources', 'ResourceInfoList', None)
        name = arn = id = 'ResourceArn'
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


@LakeFormationRegisteredLocation.filter_registry.register('cross-account')
class DataLakeLocationsCrossAccount(Filter):
    """Flags all registered datalake locations if it's cross account.

    :example:

    .. code-block:: yaml

       policies:
         - name: lakeformation-cross-account-location
           resource: aws.datalake-location
           filters:
            - type: cross-account

    """

    schema = type_schema('cross-account', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('lakeformation:ListResources',)

    def process(self, resources, event=None):
        results = []
        for r in resources:
            if self.process_account(r):
                results.append(r)
        return results

    def process_account(self, r):
        lake_bucket = {Arn.parse(r.get('ResourceArn')).resource}
        buckets = {
            b['Name'] for b in
            self.manager.get_resource_manager('s3').resources(augment=False)}
        cross_account = lake_bucket.difference(buckets)
        return cross_account
