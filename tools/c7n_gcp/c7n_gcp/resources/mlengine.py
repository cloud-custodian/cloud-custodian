# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n.utils import jmespath_search


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
        urn_component = "model"
        urn_id_segments = (-1,)  # Just use the last segment of the id in the URN

        @staticmethod
        def get(client, event):
            return client.execute_query(
                'get', {'name': jmespath_search(
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
            "jobId", "state", "createTime", "endTime"]
        get_requires_event = True
        urn_component = "job"

        @staticmethod
        def get(client, event):
            return client.execute_query(
                'get', {'name': 'projects/{}/jobs/{}'.format(
                    jmespath_search('resource.labels.project_id', event),
                    jmespath_search('protoPayload.response.jobId', event))})
