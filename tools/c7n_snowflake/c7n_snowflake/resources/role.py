# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_snowflake.provider import resources
from c7n_snowflake.query import QueryResourceManager


@resources.register("role")
class Role(QueryResourceManager):
    """
    Query, Filter, and take Action on Snowflake Role resources

    :example:

    Find roles that have been granted access to a specific warehouse

    .. code-block:: yaml

        policies:
          - name: role
            resource: snowflake.role
            filters:
              # find roles that have a grant to the C7N role
              - type: list-item
                key: grants_to
                attrs:
                  - type: value
                    key: "securable_type"
                    value: "WAREHOUSE"
                  - type: value
                    key: "securable.name"
                    value: "MY_WAREHOUSE"
    """

    client = "roles"
    object_domain = "ROLE"
    augmentations = (
        "grants_to",
        "grants_on",
        "grants_of",
        "future_grants_to",
    )
    permissions = ()
    taggable = True

    def augment(self, resources):
        resources = super(Role, self).augment(resources)

        client = self.get_client()

        for r in resources:
            resource_name = r["name"]
            for augment in self.augmentations:
                r[augment] = []
                for grant in getattr(client[resource_name], f"iter_{augment}")():
                    r[augment].append(grant.to_dict())
        return resources
