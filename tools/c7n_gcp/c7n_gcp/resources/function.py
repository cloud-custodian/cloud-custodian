# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import type_schema

from c7n_gcp.actions import MethodAction
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
        default_report_fields = [
            'name', 'runtime', 'eventTrigger.eventType', 'status', 'updateTime']

        events = {
            'create': 'google.cloud.functions.v1.CloudFunctionsService.CreateFunction',
            'delete': 'google.cloud.functions.v1.CloudFunctionsService.DeleteFunction',
            'update': 'google.cloud.functions.v1.CloudFunctionsService.UpdateFunction'}

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': (
                    'projects/{project_id}/locations/'
                    '{location_id}/functions/{function_name}').format(
                        **resource_info)})


@Function.action_registry.register('delete')
class Delete(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}
