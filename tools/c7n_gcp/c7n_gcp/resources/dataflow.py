# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
        name = id = 'name'
        get_requires_event = True
        default_report_fields = [
            'name', 'currentState', 'createTime', 'location']
        permissions = ('dataflow.jobs.list',)

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {
                    'projectId': jmespath.search('resource.labels.project_id', event),
                    'jobId': jmespath.search('protoPayload.request.job_id', event)
                }
            )
