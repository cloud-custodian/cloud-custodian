# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
