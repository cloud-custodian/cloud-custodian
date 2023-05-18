# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from googleapiclient.errors import HttpError

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n.utils import jmespath_search


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
        urn_component = "job"
        urn_region_key = 'location'
        asset_type = "dataflow.googleapis.com/Job"

        @staticmethod
        def get(client, event):
            return client.execute_command(
                'get', {
                    'projectId': jmespath_search('resource.labels.project_id', event),
                    'jobId': jmespath_search('protoPayload.request.job_id', event)
                }
            )

    def resources(self, query=None):
        query_filter = 'ACTIVE'
        if self.data.get('query'):
            query_filter = self.data['query'][0].get('filter', 'ACTIVE')

        return super(DataflowJob, self).resources(query={'filter': query_filter})

    def augment(self, resources):
        client = self.get_client()
        results = []
        for r in resources:
            ref = {
                'jobId': r['id'],
                'projectId': r['projectId'],
                'view': 'JOB_VIEW_ALL'
            }
            try:
                results.append(
                    client.execute_query(
                        'get', verb_arguments=ref))
            except HttpError:
                results.append(r)
        return results
