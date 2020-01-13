# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

from c7n.utils import type_schema

# TODO .. folder, billing account, org sink
# how to map them given a project level root entity sans use of c7n-org


@resources.register('logsink')
class LogSink(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'logging'
        version = 'v2'
        component = 'projects.sinks'
        enum_spec = ('list', 'sinks[]', None)
        scope_key = 'parent'
        scope_template = "projects/{}"
        id = "name"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', {
                'sinkName': 'projects/{project_id}/sinks/{name}'.format(
                    **resource_info)})


@resources.register('log-project-sink')
class LogProjectSink(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'logging'
        version = 'v2'
        component = 'projects.sinks'
        enum_spec = ('list', 'sinks[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}'
        id = 'name'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', {
                'sinkName': 'projects/{project_id}/sinks/{name}'.format(
                    **resource_info)})


@resources.register('log-project-metric')
class LogProjectMetric(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'logging'
        version = 'v2'
        component = 'projects.metrics'
        enum_spec = ('list', 'metrics[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}'
        id = 'name'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', {
                'metricName': 'projects/{}/metrics/{}'.format(
                    resource_info['project_id'],
                    resource_info['name'].split('/')[-1],
                )})


@LogProjectMetric.action_registry.register('delete')
class LogProjectMetric(MethodAction):
    """`Deletes <https://cloud.google.com/logging/docs/reference/v2/rest/v2/projects.metrics
    /delete>`_ a log metric

    :Example:

    .. code-block:: yaml

        policies:
          - name: metric-delete
            resource: gcp.log-project-metric
            filters:
              - type: value
                key: name
                op: eq
                value: test-metric
            actions:
              - delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    path_param_re = re.compile('projects/(.*?)/.*')

    def get_resource_params(self, m, r):
        project = self.path_param_re.match(r['metricDescriptor']['name']).groups()[0]
        return {'metricName': 'projects/{}/metrics/{}'.format(project, r['name'])}


@resources.register('log-exclusion')
class LogExclusion(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'logging'
        version = 'v2'
        component = 'exclusions'
        enum_spec = ('list', 'exclusions[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}'
        id = 'name'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', {
                'name': 'projects/{project_id}/exclusions/{name}'.format(
                    **resource_info)})
