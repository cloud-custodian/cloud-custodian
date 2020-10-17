
from c7n.actions import Action
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.utils import local_session, type_schema


class AccessPointDescribe(DescribeSource):

    def get_query_params(self, query_params):
        query_params = query_params or {}
        query_params['AccountId'] = self.manager.config.account_id
        return query_params

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('s3control')
        results = []
        for r in resources:
            ap = client.get_access_point(
                AccountId=r['AccountId'],
                Name=r['Name'])
            ap.pop('ResponseMetadata', None)
            results.append(ap)
        return results


@resources.register('s3-access-point')
class S3AccessPoint(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 's3control'
        id = name = 'PolicyId'
        enum_spec = (
            'list_access_points', 'AccessPointList', None)
        filter_name = 'PolicyIds'
        filter_type = 'list'
        arn = 'AccessPointArn'
        arn_service =  's3'
        arn_type = 'accesspoint'
        cfn_type = 'AWS::S3::AccessPoint'

    def get_source(self, source_type):
        return {'describe': AccessPointDescribe}.get(
            source_type, AccessPointDescribe)(self)


@S3AccessPoint.filter_registry.register('cross-account')
class AccessPointCrossAccount(CrossAccountAccessFilter):

    policy_attribute = 'c7n:Policy'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('s3control')
        for r in resources:
            if self.policy_attribute in r:
                continue
            r[self.policy_attribute] = client.get_access_point_policy(
                AccountId=r['AccountId'],
                Name=r['Name'])
        return super().process(resources, event)


@S3AccessPoint.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')

    def process(self, reosurces):
        client = local_session(self.manager.session_factory).client('s3control')
        for r in resources:
            try:
                client.delete_access_point(AccountId=r['AccountId'], Name=r['Name'])
            except client.NotFoundException:
                continue
        
