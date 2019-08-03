# Copyright 2018-2019 Capital One Services, LLC
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


@resources.register('dataflow-job')
class DataflowJob(QueryResourceManager):
    """GCP resource: https://cloud.google.com/dataflow/docs/reference/rest/v1b3/projects.jobs
    """

    class resource_type(TypeInfo):
        service = 'dataflow'
        version = 'v1b3'
        component = 'projects.jobs'
        enum_spec = ('aggregated', 'jobs[]', None)
        scope_key = 'projectId'
        id = 'name'
        get_requires_event = True

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {
                    'projectId': jmespath.search('resource.labels.project_id', event),
                    'jobId': jmespath.search('protoPayload.request.job_id', event)
                }
            )
