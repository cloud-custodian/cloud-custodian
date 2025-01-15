# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("athena-named-query")
class AthenaNamedQuery(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ('list_named_queries', 'NamedQueryIds', None)
        batch_detail_spec = ('batch_get_named_query', 'NamedQueryIds', None, 'NamedQueries', None)
        arn = False
        id = "NamedQueryId"
        name = "Name"
        cfn_type = "AWS::Athena::NamedQuery"


@resources.register("athena-workgroup")
class AthenaWorkGroup(query.QueryResourceManager):

    source_mapping = {
        'describe': query.DescribeWithResourceTags,
        'config': query.ConfigSource
    }

    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ('list_work_groups', 'WorkGroups', None)
        detail_spec = ('get_work_group', 'WorkGroup', 'Name', 'WorkGroup')
        arn_type = "workgroup"
        id = "Name"
        name = "Name"
        config_type = cfn_type = "AWS::Athena::WorkGroup"
        universal_taggable = object()
        permissions_augment = ("athena:ListTagsForResource",)


@resources.register("athena-data-catalog")
class AthenaDataCatalog(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ('list_data_catalogs', 'DataCatalogsSummary', None)
        arn_type = "datacatalog"
        id = "CatalogName"
        name = "CatalogName"
        config_type = cfn_type = "AWS::Athena::DataCatalog"


@resources.register('athena-capacity-reservation')
class AthenaCapacityReservation(query.QueryResourceManager):

    source_mapping = {
        'describe': query.DescribeWithResourceTags,
    }

    class resource_type(query.TypeInfo):
        service = 'athena'
        enum_spec = ('list_capacity_reservations', 'CapacityReservations', None)
        detail_spec = ('get_capacity_reservation', 'Name', 'Name', 'CapacityReservation')
        arn_type = "capacity-reservation"
        id = 'Name'
        name = 'Name'
        cfn_type = 'AWS::Athena::CapacityReservation'
        universal_taggable = object()
        permissions_augment = ('athena:ListTagsForResource',)
