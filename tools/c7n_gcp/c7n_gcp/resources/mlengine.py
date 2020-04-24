# Copyright 2019 Capital One Services, LLC
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
import jmespath

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.actions import MethodAction
from c7n.utils import type_schema, local_session


@resources.register('ml-model')
class MLModel(QueryResourceManager):
    """GCP resource: https://cloud.google.com/ml-engine/reference/rest/v1/projects.models
    """

    class resource_type(TypeInfo):
        service = 'ml'
        version = 'v1'
        component = 'projects.models'
        enum_spec = ('list', 'models[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}'
        id = 'name'
        get_requires_event = True

        @staticmethod
        def get(client, event):
            return client.execute_query(
                'get', {'name': jmespath.search(
                    'protoPayload.response.name', event
                )})


@MLModel.action_registry.register('set')
class MLModelSet(MethodAction):
    """The action is used for ML projects.models patch description field.

    GCP action is https://cloud.google.com/ml-engine/reference/rest/v1/projects.models/patch

    Example:

    .. code-block:: yaml

        policies:
          - name: ml-model-update-description
            resource: gcp.ml-model
            filters:
              - type: value
                key: name
                value: projects/cloud-custodian/models/test
            actions:
              - type: set
                description: Custom description
                labels:
                  type: new
    """

    schema = type_schema(
        'set',
        **{
            'description': {
                'type': 'string'
            },
            'labels': {
                'type': 'object',
                'additionalProperties': {
                    'type': 'string'
                }
            }
        }
    )

    method_spec = {'op': 'patch'}

    def get_resource_params(self, model, resource):
        body = {}
        if 'description' in self.data:
            body['description'] = self.data['description']
        if 'labels' in self.data:
            body['labels'] = self.data['labels']

        return {
            'name': resource['name'],
            'updateMask': ','.join(body.keys()),
            'body': body
        }


@MLModel.action_registry.register('delete')
class MLModelDelete(MethodAction):
    """The action is used for ML projects.models delete model.

    GCP action is https://cloud.google.com/ml-engine/reference/rest/v1/projects.models/delete

    Example:

    .. code-block:: yaml

        policies:
          - name: ml-model-delete
            resource: gcp.ml-model
            filters:
              - type: value
                key: name
                value: projects/cloud-custodian/models/test
            actions:
              - type: delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}


@resources.register('ml-job')
class MLJob(QueryResourceManager):
    """GCP resource: https://cloud.google.com/ml-engine/reference/rest/v1/projects.jobs
    """

    class resource_type(TypeInfo):
        service = 'ml'
        version = 'v1'
        component = 'projects.jobs'
        enum_spec = ('list', 'jobs[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}'
        id = 'name'
        get_requires_event = True

        @staticmethod
        def get(client, event):
            return client.execute_query(
                'get', {'name': 'projects/{}/jobs/{}'.format(
                    jmespath.search('resource.labels.project_id', event),
                    jmespath.search('protoPayload.response.jobId', event))})


@MLJob.action_registry.register('set')
class MLJobSet(MethodAction):
    """The action is used for ML projects.jobs patch.

    GCP action is https://cloud.google.com/ml-engine/reference/rest/v1/projects.jobs/patch

    Example:

    .. code-block:: yaml

        policies:
          - name: ml-job-set-labels
            resource: gcp.ml-job
            filters:
              - type: value
                key: jobId
                value: test_job
            actions:
              - type: set
                labels:
                  type: new
    """

    schema = type_schema(
        'set',
        **{
            'labels': {
                'type': 'object',
                'additionalProperties': {
                    'type': 'string'
                }
            }
        }
    )

    method_spec = {'op': 'patch'}

    def get_resource_params(self, model, resource):
        session = local_session(self.manager.session_factory)
        name = 'projects/{}/jobs/{}'.format(
            session.get_default_project(),
            resource['jobId'])

        body = {}
        if 'labels' in self.data:
            body['labels'] = self.data['labels']

        return {
            'name': name,
            'updateMask': ','.join(body.keys()),
            'body': body
        }
