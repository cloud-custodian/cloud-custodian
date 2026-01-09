# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json

from c7n.exceptions import CustodianError
from c7n.utils import type_schema
from snowflake.core.exceptions import NotFoundError, UnauthorizedError
from snowflake.core.warehouse import Warehouse as SnowflakeWarehouse

from c7n_snowflake.actions.base import SnowflakeAction
from c7n_snowflake.provider import resources
from c7n_snowflake.query import QueryResourceManager
from c7n_snowflake.utils import class_init_to_jsonschema


@resources.register("warehouse")
class Warehouse(QueryResourceManager):
    """
    Query, Filter, and take Action on Snowflake Warehouse resources

    Permissions:

    .. code-block:: sql

        CREATE ROLE C7N IF NOT EXISTS
        GRANT MONITOR ON WAREHOUSE $WAREHOUSE_NAME TO ROLE C7N
    """

    client = "warehouses"
    object_domain = "WAREHOUSE"
    permissions = ("MONITOR:WAREHOUSE",)
    taggable = True


@Warehouse.action_registry.register("modify")
class ModifyAction(SnowflakeAction):
    """
    Modify a Warehouse

    Permissions:

    .. code-block:: sql

        GRANT MODIFY WAREHOUSE ON $WAREHOUSE_NAME TO ROLE C7N
        GRANT MONITOR WAREHOUSE ON $WAREHOUSE_NAME TO ROLE C7N

    :example:

    .. code-block:: yaml

        policies:
            - name: modify-warehouse-auto-suspend
              description: |
                Set the auto suspend setting on all warehouses that
                have a greater than 60 or missing auto_suspend
              resource: snowflake.warehouse
              filters:
                - type: value
                  key: auto_suspend
                  value: absent
                - type: value
                  key: auto_suspend
                  value: 60
                  op: gt
              actions:
                - type: modify
                  modifications:
                    auto_suspend: 60
    """

    permissions = (
        "MODIFY:WAREHOUSE",
        "MONITOR:WAREHOUSE",
    )

    schema = type_schema(
        "modify",
        modifications=class_init_to_jsonschema(SnowflakeWarehouse),
        required=["modifications"],
    )

    def process(self, resources):
        failed = []

        client = self.manager.get_client()

        for r in resources:
            resource_name = r["name"]

            try:
                resource = client[resource_name].fetch()
            except (
                UnauthorizedError,
                NotFoundError,
            ) as e:
                error_body = json.loads(e.body)
                error_message = error_body["message"].replace("\n", " ")
                self.log.error(
                    f"Unable to fetch:{resource_name}, {error_message}. "
                    "Make sure you have granted your role 'MODIFY' and "
                    "'MONTIOR' on those resources"
                )
                failed.append(resource_name)
                continue

            for k, v in self.data["modifications"].items():
                setattr(resource, k, v)

            my_wh_res = client[r["name"]]

            try:
                my_wh_res.create_or_alter(resource)
            except (
                UnauthorizedError,
                NotFoundError,
            ) as e:
                error_body = json.loads(e.body)
                error_message = error_body["message"].replace("\n", " ")
                self.log.error(
                    f"Unable to modify:{resource_name}, {error_message}. "
                    "Make sure you have granted your role 'MODIFY' and "
                    "'MONITOR' on those warehouses"
                )
                failed.append(resource_name)
                continue

        if failed:
            raise CustodianError(f"Unable to modify resources:{failed}")
