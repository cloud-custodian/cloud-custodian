# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema, jmespath_search
from c7n_gcp.actions import MethodAction
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildTypeInfo, ChildResourceManager
from c7n_gcp.provider import resources
from c7n.utils import local_session, type_schema
from c7n.filters.core import OPERATORS
from c7n.filters import ValueFilter


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
        enum_spec = ('list', 'jobs[]', {'allUsers': True})
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

    def get_resource_params(self, model, r):
        return {
            'projectId': r['tableReference']['projectId'],
            'datasetId': r['tableReference']['datasetId'],
            'tableId': r['tableReference']['tableId']
        }


@BigQueryTable.filter_registry.register('encryption-configuration-bigquery-filter')
class RetentionPolicyBucketFilter(ValueFilter):
    schema = type_schema('encryption-configuration-bigquery-filter',
                         rinherit=ValueFilter.schema, )
    permissions = ('storage.buckets.list',)

    def _perform_op(self, a, b):
        if self.data['value'] == 'present' and a:
            return True
        if self.data['value'] == 'absent' and a is None:
            return True
        if a is not None:
            op = OPERATORS[self.data.get('op', 'eq')]
            return op(a, b)
        return False

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        client = session.client(service_name='bigquery', version='v2', component='tables')
        # Getting project_id from client
        project = session.get_default_project()
        accepted_resources = []
        value = self.data['value']
        for resource in resources:
            encryption_configuration = client.execute_query('get', {
                'projectId': project, 'datasetId': resource['tableReference']['datasetId'],
                'tableId': resource['tableReference']['tableId']})
            jmespath_key = jmespath.search(self.data['key'], encryption_configuration)
            if self._perform_op(jmespath_key, value):
                accepted_resources.append(resource)

        return accepted_resources
