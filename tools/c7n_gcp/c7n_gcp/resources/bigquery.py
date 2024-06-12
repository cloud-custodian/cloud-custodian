# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema, jmespath_search
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildTypeInfo, ChildResourceManager
from c7n_gcp.provider import resources
from c7n_gcp.actions import MethodAction


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
        scc_type = "google.cloud.bigquery.Dataset"
        metric_key = "resource.labels.dataset_id"
        permissions = ('bigquery.datasets.get',)
        urn_component = "dataset"
        urn_id_path = "datasetReference.datasetId"

        @staticmethod
        def get(client, event):
            # dataset creation doesn't include data set name in resource name.
            if 'protoPayload' in event:
                _, method = event['protoPayload']['methodName'].split('.')
                if method not in ('insert', 'update'):
                    raise RuntimeError("unknown event %s" % event)
                expr = 'protoPayload.serviceData.dataset{}Response.resource.datasetName'.format(
                    method.capitalize())
                ref = jmespath_search(expr, event)
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
        enum_spec = ('list', 'jobs[]', {'allUsers': True, 'projection': 'full'})
        get_requires_event = True
        scope = 'project'
        scope_key = 'projectId'
        name = id = 'id'
        default_report_fields = ["id", "user_email", "status.state"]
        urn_component = "job"

        @staticmethod
        def get(client, event):
            return client.execute_query('get', {
                'projectId': jmespath_search('resource.labels.project_id', event),
                'jobId': jmespath_search(
                    'protoPayload.metadata.tableCreation.jobName', event
                ).rsplit('/', 1)[-1]
            })

        @classmethod
        def _get_urn_id(cls, resource):
            jobRef = resource['jobReference']
            return f"{jobRef['location']}/{jobRef['jobId']}"


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
        urn_component = "table"
        urn_id_path = "tableReference.tableId"

        @classmethod
        def _get_urn_id(cls, resource):
            tableRef = resource['tableReference']
            return f"{tableRef['datasetId']}/{tableRef['tableId']}"

        @staticmethod
        def get(client, event):
            return client.execute_query('get', {
                'projectId': event['project_id'],
                'datasetId': event['dataset_id'],
                'tableId': event['resourceName'].rsplit('/', 1)[-1]
            })

    def augment(self, resources):
        client = self.get_client()
        results = []
        for r in resources:
            ref = r['tableReference']
            results.append(
                client.execute_query(
                    'get', verb_arguments=ref))
        return results


@BigQueryTable.action_registry.register('delete')
class DeleteBQTable(MethodAction):
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('bigquery.tables.get', 'bigquery.tables.delete')

    @staticmethod
    def get_resource_params(model, r):
        return {
            'projectId': r['tableReference']['projectId'],
            'datasetId': r['tableReference']['datasetId'],
            'tableId': r['tableReference']['tableId']
        }


@DataSet.action_registry.register('delete')
class DeleteDataSet(MethodAction):
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('bigquery.dataset.get', 'bigquery.dataset.delete')

    @staticmethod
    def get_resource_params(model, r):
        return {
            'projectId': r['datasetReference']['projectId'],
            'datasetId': r['datasetReference']['datasetId']
        }
