# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import jmespath

from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildTypeInfo, ChildResourceManager
from c7n_gcp.provider import resources


@resources.register('bq-dataset')
class DataSet(QueryResourceManager):
    """GCP resource: https://cloud.google.com/bigquery/docs/reference/rest/v2/datasets
    """
    class resource_type(TypeInfo):
        service = 'bigquery'
        version = 'v2'
        component = 'datasets'
        enum_spec = ('list', 'datasets[]', None)
        scope = 'project'
        scope_key = 'projectId'
        get_requires_event = True
        id = "id"
        name = "friendlyName"
        default_report_fields = [
            id, name, "description",
            "creationTime", "lastModifiedTime"]
        asset_type = "bigquery.googleapis.com/Dataset"
        permissions = ('bigquery.datasets.get',)

        @staticmethod
        def get(client, event):
            # dataset creation doesn't include data set name in resource name.
            if 'protoPayload' in event:
                _, method = event['protoPayload']['methodName'].split('.')
                if method not in ('insert', 'update'):
                    raise RuntimeError("unknown event %s" % event)
                expr = 'protoPayload.serviceData.dataset{}Response.resource.datasetName'.format(
                    method.capitalize())
                ref = jmespath.search(expr, event)
            else:
                ref = event
            return client.execute_query('get', verb_arguments=ref)

    def augment(self, resources):
        client = self.get_client()
        results = []
        for r in resources:
            ref = r['datasetReference']
            results.append(
                client.execute_query(
                    'get', verb_arguments=ref))
        return results


@resources.register('bq-job')
class BigQueryJob(QueryResourceManager):
    """GCP resource: https://cloud.google.com/bigquery/docs/reference/rest/v2/jobs
    """
    # its unclear why this is needed
    class resource_type(TypeInfo):
        service = 'bigquery'
        version = 'v2'
        component = 'jobs'
        enum_spec = ('list', 'jobs[]', {'allUsers': True})
        get_requires_event = True
        scope = 'project'
        scope_key = 'projectId'
        name = id = 'id'
        default_report_fields = ["id", "user_email", "status.state"]

        @staticmethod
        def get(client, event):
            return client.execute_query('get', {
                'projectId': jmespath.search('resource.labels.project_id', event),
                'jobId': jmespath.search(
                    'protoPayload.metadata.tableCreation.jobName', event
                ).rsplit('/', 1)[-1]
            })


@resources.register('bq-table')
class BigQueryTable(ChildResourceManager):
    """GCP resource: https://cloud.google.com/bigquery/docs/reference/rest/v2/tables
    """

    class resource_type(ChildTypeInfo):
        service = 'bigquery'
        version = 'v2'
        component = 'tables'
        enum_spec = ('list', 'tables[]', None)
        scope_key = 'projectId'
        id = 'id'
        name = "friendlyName"
        default_report_fields = [
            id, name, "description", "creationTime", "lastModifiedTime", "numRows", "numBytes"]
        parent_spec = {
            'resource': 'bq-dataset',
            'child_enum_params': [
                ('datasetReference.datasetId', 'datasetId'),
            ],
            'parent_get_params': [
                ('tableReference.projectId', 'projectId'),
                ('tableReference.datasetId', 'datasetId'),
            ]
        }
        asset_type = "bigquery.googleapis.com/Table"

        @staticmethod
        def get(client, event):
            return client.execute_query('get', {
                'projectId': event['project_id'],
                'datasetId': event['dataset_id'],
                'tableId': event['resourceName'].rsplit('/', 1)[-1]
            })
