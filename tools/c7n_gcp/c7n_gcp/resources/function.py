# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import type_schema

from c7n_gcp.actions import MethodAction
from c7n_gcp.filters import IamPolicyFilter
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('function')
class Function(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudfunctions'
        version = 'v1'
        component = 'projects.locations.functions'
        enum_spec = ('list', 'functions[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = "projects/{}/locations/-"
        name = id = "name"
        metric_key = "resource.labels.function_name"
        default_report_fields = [
            'name', 'runtime', 'eventTrigger.eventType', 'status', 'updateTime']

        events = {
            'create': 'google.cloud.functions.v1.CloudFunctionsService.CreateFunction',
            'delete': 'google.cloud.functions.v1.CloudFunctionsService.DeleteFunction',
            'update': 'google.cloud.functions.v1.CloudFunctionsService.UpdateFunction'}
        urn_component = "function"
        asset_type = "cloudfunctions.googleapis.com/CloudFunction"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': (
                    'projects/{project_id}/locations/'
                    '{location_id}/functions/{function_name}').format(
                        **resource_info)})

        @classmethod
        def _get_location(cls, resource):
            "The region is the fourth segment of the name."
            return resource["name"].split('/')[3]

        @classmethod
        def _get_urn_id(cls, resource):
            "The id is the last segment of the name ."
            return resource["name"].split('/', 6)[-1]


@Function.filter_registry.register('iam-policy')
class FunctionIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process function resources correctly.
    """
    permissions = ('cloudfunctions.functions.getIamPolicy',)


@Function.action_registry.register('delete')
class Delete(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}
