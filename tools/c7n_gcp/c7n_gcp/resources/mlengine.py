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


@resources.register('ml-model')
class MLModel(QueryResourceManager):
    """GCP Resource
    https://cloud.google.com/ai-platform/prediction/docs/reference/rest/v1/projects.models
    """
    class resource_type(TypeInfo):
        service = 'ml'
        version = 'v1'
        component = 'projects.models'
        enum_spec = ('list', 'models[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = [
            id, name, "description", "onlinePredictionLogging"]
        get_requires_event = True

        @staticmethod
        def get(client, event):
            return client.execute_query(
                'get', {'name': jmespath.search(
                    'protoPayload.response.name', event
                )})


@resources.register('ml-job')
class MLJob(QueryResourceManager):
    """GCP Resource
    https://cloud.google.com/ai-platform/prediction/docs/reference/rest/v1/projects.jobs
    """
    class resource_type(TypeInfo):
        service = 'ml'
        version = 'v1'
        component = 'projects.jobs'
        enum_spec = ('list', 'jobs[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = 'jobId'
        default_report_fields = [
            "jobId", "status", "createTime", "endTime"]
        get_requires_event = True

        @staticmethod
        def get(client, event):
            return client.execute_query(
                'get', {'name': 'projects/{}/jobs/{}'.format(
                    jmespath.search('resource.labels.project_id', event),
                    jmespath.search('protoPayload.response.jobId', event))})
