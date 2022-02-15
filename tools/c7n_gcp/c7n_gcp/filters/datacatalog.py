# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import local_session, type_schema
from c7n.filters import Filter, FilterValidationError
import json


class DataCatalogSearchFilter(Filter):
    """Filter resources via Data Catalog search

    Filters resources by a catalog search of the provided query.

    The filter retrieves high-level metadata about the retrieved data
    resources. This metadata is then used by resource-specific
    implementations to retrieve the actual resource objects.

    The scope of the search includes parameters for `include_gcp_public_datasets` (boolean),
    `include_org_ids` (array of strings), `include_project_ids` (array of strings), and
    `restricted_locations` (array of strings). Providing these values gives context for what
    organizations, projects, and locations your search will retrieve resources from, and whether
    GCP public datasets will be included.

    The `query` parameter (string) gives the specifications of the resources you want
    to search for. For example, to retrieve all BigQuery tables in a GCP project named
    `my-gcp-project` that are marked with a tag template called `BQ Table Ownership` with
    a `ResourceOwner` tag equal to value `test123@gmail.com`, your query could be:
    `"tag=my-gcp-project.bq_table_ownership AND type=table AND tag:resourceowner:test123@gmail.com"`
    An empty query string will retrieve all data resources contained in the provided scope
    that the user has access to. More information about writing a query can be found at
    https://cloud.google.com/data-catalog/docs/how-to/search-reference.

    The optional `order_by` field specifies the order in which your retrieved resources
    are returned. Possible values include `relevance`, `last_modified_timestamp [asc|desc]`,
    and `default`. If `order_by` is not specified, this will default to `relevance` descending.


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
    schema = type_schema(
        'tag-template',
        include_gcp_public_datasets={'type': 'boolean'},
        include_org_ids={'type': 'array', 'items': {'type': 'string'}},
        include_project_ids={'type': 'array', 'items': {'type': 'string'}},
        restricted_locations={'type': 'array', 'items': {'type': 'string'}},
        query={'type': 'string'},
        order_by={'type': 'string'})

    def validate(self):
        include_org_ids = self.data.get('include_org_ids')
        include_project_ids = self.data.get('include_project_ids')
        include_gcp_public_datasets = self.data.get('include_gcp_public_datasets')
        if not include_org_ids and not include_project_ids and not include_gcp_public_datasets:
            raise FilterValidationError(
                """Invalid scope provided. Tag Template filter cannot have missing values for both
                    include_org_ids and include_project_ids with include_gcp_public_datasets set to
                    False:{include_org_ids}, {include_project_ids}, {include_gcp_public_datasets}
                    in {self.manager.data}""")
        return self

    def data_catalog_modify(self, resource, info):
        resource['c7n:data-catalog'] = info
        return resource

    def process(self, resources, event=None):
        self.include_gcp_public_datasets = json.loads(
            self.data.get('include_gcp_public_datasets', False))
        self.include_org_ids = self.data.get('include_org_ids')
        self.include_project_ids = self.data.get('include_project_ids')
        self.restricted_locations = self.data.get('restricted_locations')
        self.query = self.data.get('query')
        self.order_by = self.data.get('order_by', 'relevance')
        config = {
            'scope': {
                'includeGcpPublicDatasets': self.include_gcp_public_datasets,
                'includeOrgIds': self.include_org_ids,
                'includeProjectIds': self.include_project_ids,
            },
            'orderBy': self.order_by
        }
        if self.restricted_locations:
            config['scope']['restrictedLocations'] = self.restricted_locations
        if self.query:
            config['query'] = self.query

        session = local_session(self.manager.session_factory)
        client = session.client('datacatalog', 'v1beta1', 'catalog')
        retrieved = client.execute_command('search', {'body': config}).get('results')
        return retrieved
