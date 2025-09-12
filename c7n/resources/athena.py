# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.manager import resources
from c7n import query
from c7n.utils import type_schema, local_session
from c7n.filters.core import ValueFilter

from .aws import shape_validate
from botocore.exceptions import ClientError


@resources.register("athena-named-query")
class AthenaNamedQuery(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ("list_named_queries", "NamedQueryIds", None)
        batch_detail_spec = ("batch_get_named_query", "NamedQueryIds", None, "NamedQueries", None)
        arn = False
        id = "NamedQueryId"
        name = "Name"
        cfn_type = "AWS::Athena::NamedQuery"


@resources.register("athena-work-group")
class AthenaWorkGroup(query.QueryResourceManager):
    source_mapping = {"describe": query.DescribeWithResourceTags, "config": query.ConfigSource}

    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ("list_work_groups", "WorkGroups", None)
        detail_spec = ("get_work_group", "WorkGroup", "Name", "WorkGroup")
        arn_type = "workgroup"
        id = "Name"
        name = "Name"
        config_type = cfn_type = "AWS::Athena::WorkGroup"
        universal_taggable = object()
        permissions_augment = ("athena:ListTagsForResource",)


@AthenaWorkGroup.action_registry.register("update")
class UpdateWorkGroup(Action):
    schema = type_schema(
        "update", config={"type": "object", "minProperties": 1}, required=("config",)
    )
    shape = "UpdateWorkGroupInput"
    permissions = ("athena:UpdateWorkGroup",)

    def validate(self):
        config = dict(self.data.get("config", {}))
        params = {}
        params["WorkGroup"] = "abc"
        params["Description"] = ""
        params["ConfigurationUpdates"] = config
        shape_validate(params, self.shape, "athena")

    def process(self, resources):
        client = local_session(self.manager.session_factory).client("athena")
        config = dict(self.data.get("config", {}))
        for r in self.filter_resources(resources, "State", "ENABLED"):
            client.update_work_group(
                WorkGroup=r["Name"], Description=r["Description"], ConfigurationUpdates=config
            )


@resources.register("athena-data-catalog")
class AthenaDataCatalog(query.QueryResourceManager):
    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }

    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ("list_data_catalogs", "DataCatalogsSummary", None)
        arn_type = "datacatalog"
        id = "CatalogName"
        name = "CatalogName"
        config_type = cfn_type = "AWS::Athena::DataCatalog"
        universal_taggable = object()
        permissions_augment = ("athena:ListTagsForResource",)


@resources.register("athena-capacity-reservation")
class AthenaCapacityReservation(query.QueryResourceManager):
    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }

    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ("list_capacity_reservations", "CapacityReservations", None)
        arn_type = "capacity-reservation"
        id = "Name"
        name = "Name"
        cfn_type = "AWS::Athena::CapacityReservation"
        universal_taggable = object()
        permissions_augment = ("athena:ListTagsForResource",)


@AthenaCapacityReservation.action_registry.register("cancel")
class DeleteReservation(Action):
    schema = type_schema("cancel")
    permissions = ("athena:CancelCapacityReservation",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client("athena")
        for r in self.filter_resources(resources, "Status", ("ACTIVE", "PENDING")):
            client.cancel_capacity_reservation(Name=r["Name"])


@resources.register("athena-query-execution")
class AthenaQueryExecution(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ("list_query_executions", "QueryExecutionIds", None)
        detail_spec = ("get_query_execution", "QueryExecutionId", None, "QueryExecution")
        batch_detail_spec = (
            "batch_get_query_execution",
            "QueryExecutionIds",
            None,
            "QueryExecutions",
            None,
        )
        arn = False
        id = "QueryExecutionId"
        name = "QueryExecutionId"


@AthenaQueryExecution.filter_registry.register("runtime-statistics")
class RuntimeStatisticsFilter(ValueFilter):
    schema = type_schema("runtime-statistics", rinherit=ValueFilter.schema)
    permissions = ("athena:GetQueryRuntimeStatistics",)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client("athena")
        for r in resources:
            if "QueryExecutionId" not in r:
                # Ensure we have full detail loaded via batch detail
                continue
            # Fetch on-demand and attach for filtering
            try:
                resp = client.get_query_runtime_statistics(
                    QueryExecutionId=r["QueryExecutionId"]
                )
                stats = resp.get("QueryRuntimeStatistics")
                if stats is not None:
                    r["QueryRuntimeStatistics"] = stats
            except ClientError:
                # If API is not available/authorized, leave as-is and let matching fail
                pass
        return super(RuntimeStatisticsFilter, self).process(resources, event)
