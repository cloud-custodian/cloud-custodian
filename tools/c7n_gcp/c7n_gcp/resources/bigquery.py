# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema, jmespath_search
from c7n.exceptions import PolicyValidationError
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildTypeInfo, ChildResourceManager
from c7n_gcp.provider import resources
from c7n_gcp.actions import MethodAction
from c7n_gcp.filters.recommender import RecommenderFilter


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
        labels = True
        labels_op = 'patch'
        labels_perm = 'update'

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

        @staticmethod
        def get_label_params(resource, all_labels):
            return {**resource['datasetReference'], 'body': {'labels': all_labels}}

    def augment(self, resources):
        client = self.get_client()
        results = []
        for r in resources:
            ref = r['datasetReference']
            results.append(
                client.execute_query(
                    'get', verb_arguments=ref))
        return results

    def get_resource_query(self):
        if 'query' in self.data:
            for child in self.data.get('query'):
                if 'filter' in child:
                    return {'filter': child['filter']}


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
        # Jobs have labels but no update method, so no labels action

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
            ],
            'use_child_query': True,
        }
        asset_type = "bigquery.googleapis.com/Table"
        urn_component = "table"
        urn_id_path = "tableReference.tableId"
        labels = True
        labels_op = 'patch'
        labels_perm = 'update'

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

        @staticmethod
        def get_label_params(resource, all_labels):
            return {**resource['tableReference'], 'body': {'labels': all_labels}}

    def augment(self, resources):
        client = self.get_client()
        results = []
        for r in resources:
            ref = r['tableReference']
            results.append(client.execute_query('get', verb_arguments=ref))
        return results

    def get_resource_query(self):
        # Allow query values to be consumed by parent dataset listing only.
        # BigQuery tables.list does not accept a top-level "filter" argument.
        return None


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


@BigQueryTable.filter_registry.register('recommend')
class BigQueryTableRecommenderFilter(RecommenderFilter):

    def match_ids(self, rids, resources):
        normalized_rids = set()
        for rid in rids:
            normalized_rids.add('projects/{}'.format(rid.split('/projects/', 1)[1]))

        for resource in resources:
            table_ref = resource.get('tableReference', {})
            table_rid = "projects/{}/datasets/{}/tables/{}".format(
                table_ref.get('projectId', ''),
                table_ref.get('datasetId', ''),
                table_ref.get('tableId', '')
            )
            if table_rid in normalized_rids:
                yield resource


@DataSet.action_registry.register('delete')
class DeleteDataSet(MethodAction):
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('bigquery.datasets.get', 'bigquery.datasets.delete')

    @staticmethod
    def get_resource_params(model, r):
        return {
            'projectId': r['datasetReference']['projectId'],
            'datasetId': r['datasetReference']['datasetId']
        }


@DataSet.action_registry.register('update')
class UpdateDataSet(MethodAction):
    """Update BigQuery dataset attributes.

    This action supports partial updates via the BigQuery datasets.patch API.

    :example:

    .. code-block:: yaml

        policies:
          - name: bq-dataset-update-access
            resource: gcp.bq-dataset
            filters:
              - type: value
                key: id
                op: contains
                value: c7n_bq_dataset
            actions:
              - type: update
                access:
                  - role: READER
                    userByEmail: analyst@example.com
    """

    schema = type_schema(
        'update',
        **{
            'access': {'type': 'array', 'items': {'type': 'object'}},
            'description': {'type': 'string'},
            'friendlyName': {'type': 'string'},
            'defaultTableExpirationMs': {'type': 'string'},
            'defaultPartitionExpirationMs': {'type': 'string'},
            'maxTimeTravelHours': {'type': 'string'},
            'storageBillingModel': {'type': 'string'},
        }
    )
    method_spec = {'op': 'patch'}
    method_perm = 'update'
    permissions = ('bigquery.datasets.get', 'bigquery.datasets.update')
    update_fields = (
        'access',
        'description',
        'friendlyName',
        'defaultTableExpirationMs',
        'defaultPartitionExpirationMs',
        'maxTimeTravelHours',
        'storageBillingModel',
    )

    def validate(self):
        super().validate()
        if not any(field in self.data for field in self.update_fields):
            raise PolicyValidationError(
                "policy:{} action:{} requires at least one mutable dataset field".format(
                    self.manager.ctx.policy.name, self.type
                )
            )
        return self

    def get_resource_params(self, model, r):
        body = {}
        for field in UpdateDataSet.update_fields:
            if field in self.data:
                body[field] = self.data[field]

        return {
            'projectId': r['datasetReference']['projectId'],
            'datasetId': r['datasetReference']['datasetId'],
            'body': body
        }


@DataSet.action_registry.register('set-access')
class SetDataSetAccess(MethodAction):
    """Add or remove entries in a BigQuery dataset's access list.

    The BigQuery datasets.patch API replaces the entire ``access`` array, so
    this action reads each dataset's current ``access`` entries, applies the
    ``add`` and ``remove`` lists, and patches the dataset with the result.
    Existing entries not affected by either list are kept.

    ``add`` entries are appended unless an equal entry already exists.
    ``remove`` entries are match criteria: an existing entry is removed when
    every key in a criterion equals the entry's value for that key. An ``add``
    entry that also matches a ``remove`` criterion fails validation.

    Roles may be given in either the legacy form (``READER``) or the IAM form
    (``roles/bigquery.dataViewer``); BigQuery returns only the legacy form.

    Datasets whose access list would not change are not patched.

    :example:

    Remove public access from datasets (CIS GCP Foundations 7.1)

    .. code-block:: yaml

        policies:
          - name: bq-dataset-remove-public-access
            resource: gcp.bq-dataset
            filters:
              - or:
                - type: value
                  key: access[].iamMember
                  op: contains
                  value: allUsers
                - type: value
                  key: access[].specialGroup
                  op: contains
                  value: allAuthenticatedUsers
            actions:
              - type: set-access
                remove:
                  - iamMember: allUsers
                  - specialGroup: allAuthenticatedUsers

    :example:

    Grant a group read access to datasets

    .. code-block:: yaml

        policies:
          - name: bq-dataset-grant-analysts
            resource: gcp.bq-dataset
            actions:
              - type: set-access
                add:
                  - role: READER
                    groupByEmail: analysts@example.com
    """

    member_fields = (
        'specialGroup',
        'iamMember',
        'userByEmail',
        'groupByEmail',
        'domain',
    )
    legacy_roles = {
        'roles/bigquery.dataOwner': 'OWNER',
        'roles/bigquery.dataEditor': 'WRITER',
        'roles/bigquery.dataViewer': 'READER',
    }
    entry_properties = {field: {'type': 'string'} for field in ('role',) + member_fields}

    schema = type_schema(
        'set-access',
        add={
            'type': 'array',
            'minItems': 1,
            'items': {
                'type': 'object',
                'required': ['role'],
                'additionalProperties': False,
                'properties': entry_properties,
                'oneOf': [{'required': [field]} for field in member_fields],
            },
        },
        remove={
            'type': 'array',
            'minItems': 1,
            'items': {
                'type': 'object',
                'minProperties': 1,
                'additionalProperties': False,
                'properties': entry_properties,
            },
        },
    )
    method_spec = {'op': 'patch'}
    method_perm = 'update'
    permissions = ('bigquery.datasets.get', 'bigquery.datasets.update')

    def validate(self):
        super().validate()
        if 'add' not in self.data and 'remove' not in self.data:
            raise PolicyValidationError(
                f"policy:{self.manager.ctx.policy.name} action:{self.type} "
                "requires at least one of add or remove"
            )
        conflicts = [entry for entry in self.data.get('add', ()) if self.is_removed(entry)]
        if conflicts:
            raise PolicyValidationError(
                f"policy:{self.manager.ctx.policy.name} action:{self.type} "
                f"add entries also match remove: {conflicts}"
            )
        return self

    def process(self, resources):
        resources = [r for r in resources if self.get_access(r) != r.get('access', [])]
        if resources:
            super().process(resources)

    def normalize(self, entry):
        entry = dict(entry)
        if 'role' in entry:
            entry['role'] = self.legacy_roles.get(entry['role'], entry['role'])
        return entry

    def is_removed(self, entry):
        entry = self.normalize(entry)
        return any(
            all(entry.get(k) == v for k, v in self.normalize(criterion).items())
            for criterion in self.data.get('remove', ())
        )

    def get_access(self, r):
        access = list(r.get('access', []))
        existing = [self.normalize(entry) for entry in access]
        for entry in self.data.get('add', ()):
            if self.normalize(entry) not in existing:
                access.append(entry)
                existing.append(self.normalize(entry))
        return [entry for entry in access if not self.is_removed(entry)]

    def get_resource_params(self, model, r):
        return {
            'projectId': r['datasetReference']['projectId'],
            'datasetId': r['datasetReference']['datasetId'],
            'body': {'access': self.get_access(r)},
        }
