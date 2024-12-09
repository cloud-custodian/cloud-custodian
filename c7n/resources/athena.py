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
        permissions_augment = ("athena:ListTagsForResource",)


@resources.register("athena-workgroup")
class AthenaWorkGroup(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ('list_work_groups', 'WorkGroups', None)
        detail_spec = ('get_work_group', 'Name', 'Name', 'WorkGroup')
        arn = "Arn"
        id = "Name"
        name = "Name"
        cfn_type = "AWS::Athena::WorkGroup"
        permissions_augment = ("athena:ListTagsForResource",)


@resources.register("athena-data-catalog")
class AthenaDataCatalog(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ('list_data_catalogs', 'DataCatalogsSummary', None)
        detail_spec = ('get_data_catalog', 'Name', 'Name', 'DataCatalog')
        arn = "Arn"
        id = "Name"
        name = "Name"
        cfn_type = "AWS::Athena::DataCatalog"
        permissions_augment = ("athena:ListTagsForResource",)


@resource.register('athena-capacity-reservation')
class AthenaCapacityReservation(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'athena'
        enum_spec = ('list_capacity_reservations', 'CapacityReservations', None)
        detail_spec = ('get_capacity_reservation', 'CapacityReservationId', 'CapacityReservationId', 'CapacityReservation')
        arn = 'CapacityReservationArn'
        id = 'CapacityReservationId'
        name = 'CapacityReservationId'
        cfn_type = 'AWS::Athena::CapacityReservation'
        permissions_augment = ('athena:ListTagsForResource',)