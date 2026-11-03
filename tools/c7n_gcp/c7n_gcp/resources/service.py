# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.utils import chunks, local_session, type_schema


class DescribeService(DescribeSource):

    def get_resources(self, query):
        if not query or 'names' not in query:
            return super().get_resources(query)
        # https://cloud.google.com/service-usage/docs/reference/rest/v1/services/batchGet
        session = local_session(self.manager.session_factory)
        client = self.manager.get_client()
        parent = 'projects/{}'.format(session.get_default_project())
        results = []
        for batch in chunks(query['names'], 30):
            results.extend(client.execute_query('batchGet', {
                'parent': parent,
                'names': ['{}/services/{}'.format(parent, n) for n in batch]}
            ).get('services', []))
        return results

    def get_permissions(self):
        if 'names' in self.manager.get_resource_query():
            return ('serviceusage.services.get',)
        return super().get_permissions()


@resources.register('service')
class Service(QueryResourceManager):
    """GCP Service Usage Management

    By default only enabled services are listed. To check specific
    services regardless of their state, pass their names with ``query``.
    They are fetched directly, so disabled services are included.

    :example:

    Find projects where the Cloud Asset API is disabled

    .. code-block:: yaml

      policies:
        - name: gcp-cloud-asset-api-disabled
          resource: gcp.service
          query:
            - names:
                - cloudasset.googleapis.com
          filters:
            - state: DISABLED

    https://cloud.google.com/service-usage/docs/reference/rest
    https://cloud.google.com/service-infrastructure/docs/service-management/reference/rest/v1/services
    """
    class resource_type(TypeInfo):
        service = 'serviceusage'
        version = 'v1'
        component = 'services'
        enum_spec = ('list', 'services[]', {'pageSize': 200})
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = [name, "state"]
        asset_type = 'serviceusage.googleapis.com/Service'
        urn_component = "service"
        urn_id_segments = (-1,)  # Just use the last segment of the id in the URN

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {'name': resource_info['resourceName']})

    def get_source(self, source_type):
        if source_type == 'describe-gcp':
            return DescribeService(self)
        return super().get_source(source_type)

    def get_resource_query(self):
        # https://cloud.google.com/service-usage/docs/reference/rest/v1/services/list
        # default to just listing enabled services. Listing disabled services
        # returns every service available to the project (thousands) against
        # a much lower rate quota, so specific services are fetched by name.
        names = [n for q in self.data.get('query', ()) for n in q.get('names', ())]
        if names:
            return {'names': names}
        return {'filter': 'state:ENABLED'}


@Service.action_registry.register('enable')
class Enable(MethodAction):
    """Enable a service for the current project

    Example::

      policies:
        - name: enable-cloud-asset-api
          resource: gcp.service
          query:
            - names:
                - cloudasset.googleapis.com
          filters:
            - state: DISABLED
          actions:
            - enable
    """

    schema = type_schema('enable')
    method_spec = {'op': 'enable'}

    def get_resource_params(self, model, resource):
        return {'name': resource['name'], 'body': {}}


@Service.action_registry.register('disable')
class Disable(MethodAction):
    """Disable a service for the current project

    Example::

      policies:
        - name: disable-disallowed-services
          resource: gcp.service
          mode:
            type: gcp-audit
            methods:
             - google.api.servicemanagement.v1.ServiceManagerV1.ActivateServices
          filters:
           - config.name: translate.googleapis.com
          actions:
           - disable
    """

    schema = type_schema(
        'disable',
        dependents={'type': 'boolean', 'default': False},
        usage={'enum': ['SKIP', 'CHECK']})

    method_spec = {'op': 'disable'}

    def get_resource_params(self, model, resource):
        return {'name': resource['name'],
                'body': {
                    'disableDependentServices': self.data.get('dependents', False),
                    'checkIfServiceHasUsage': self.data.get(
                        'usage', 'CHECK_IF_SERVICE_HAS_USAGE_UNSPECIFIED')}}
