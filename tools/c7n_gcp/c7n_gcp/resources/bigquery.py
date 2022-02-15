# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import jmespath
import re

from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildTypeInfo, ChildResourceManager
from c7n_gcp.provider import resources
from c7n_gcp.filters.datacatalog import DataCatalogSearchFilter
from c7n.utils import type_schema


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
        metric_key = "resouece.labels.dataset_id"
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


@BigQueryTable.filter_registry.register('data-catalog')
class BigQueryTableDataCatalogFilter(DataCatalogSearchFilter):
    """
    Filter BigQuery Table resources via Data Catalog's catalog search by
    carrying out a Data Catalog search, parsing the returned metadata,
    and identifying all matching resources.

    :example:

    .. code-block :: yaml

       policies:
        - name: bq-tables-tag-template-resourceowner
          resource: gcp.bq-table
          filters:
            - type: data-catalog
              include_gcp_public_datasets: false
              include_org_ids:
                - 112233445566
              include_project_ids:
                - my-gcp-project
              query: "tag=my-gcp-project.bq_table_ownership AND tag:resourceowner:test@gmail.com"

    """
    schema = type_schema('data-catalog', rinherit=DataCatalogSearchFilter.schema)
    permissions = ('bigquery.tables.get',)

    def get_resource_id(self, resource):
        path_param_re = re.compile('.*?/projects/(.*?)/datasets/(.*?)/tables/(.*)')
        project, dataset, table = path_param_re.match(resource['linkedResource']).groups()
        id = f'{project}:{dataset}.{table}'
        return id

    def process(self, resources, event=None):
        tables = super(BigQueryTableDataCatalogFilter, self).process(resources, None)
        resources_dict = {r.get('id'): r for r in resources}
        filtered_tables = []
        for t in tables:
            table_id = self.get_resource_id(t)
            if resources_dict.get(table_id):
                resource = super(BigQueryTableDataCatalogFilter, self).data_catalog_modify(
                    resources_dict.get(table_id), t)
                filtered_tables.append(resource)
        return filtered_tables
