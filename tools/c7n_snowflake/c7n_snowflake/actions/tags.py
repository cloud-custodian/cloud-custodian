# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os

from c7n.exceptions import CustodianError
from c7n.utils import type_schema
from snowflake.core.exceptions import NotFoundError, UnauthorizedError

from c7n_snowflake.actions.base import SnowflakeAction


class SnowflakeTagAction(SnowflakeAction):
    """
    Tag a Snowflake resource

    :example:

    .. code-block:: yaml

        policies:
          - name: tag-warehouse-with-custom-tag
            description: tag a warehouse with a custom tag
            resource: snowflake.warehouse
            filters:
              - name: MY_WH
            actions:
              - type: tag
                # creates the tag if it doesnt exist, default: False
                create_tags_in_system: true
                tags:
                  Test: bar
    """

    permissions = ()

    schema = type_schema(
        'tag', tags={'type': 'object'}, create_tags_in_system={'type': 'boolean', 'default': False}
    )

    def validate(self):
        if not os.environ.get('SNOWFLAKE_TAG_DATABASE'):
            raise CustodianError(
                "Tag actions require the environment variable 'SNOWFLAKE_TAG_DATABASE'"
            )
        return self

    def create_system_tag(self, session, tag_name: str):
        """
        Creates Tag in Snowflake system
        """
        self.log.info(f"Creating tag in system:{tag_name}")
        create_command = session.sql(
            f"CREATE TAG IF NOT EXISTS {tag_name} "
            "COMMENT = 'Created by Cloud Custodian'"
        )
        create_command.collect()

    def fetch_system_tags(self, session, tag_database: str, tag_schema: str) -> set:
        """
        Fetch the set of system tags from Snowflake
        """
        tags = set()
        all_tags_query = session.sql("show tags")
        iterator = all_tags_query.to_local_iterator()
        for tag_row in iterator:
            tags.add(tag_row.name.lower())

        return tags

    def get_missing_tags(self, system_tags: set[str], policy_tags: set[str]) -> set[str]:
        """
        Returns the set of tag names that are in the policy but not available
        in the system tags.
        """
        return policy_tags.difference(system_tags)

    def tag_resource(self, session, resource: dict, tags: dict):
        resource_name = resource['name']
        object_domain = self.manager.object_domain

        for k, v in tags.items():
            command = session.sql(f"ALTER {object_domain} {resource_name} SET TAG {k}='{v}'")
            command.collect()
        return

    def process(self, resources: list[dict]):
        tag_database = os.environ.get("SNOWFLAKE_TAG_DATABASE")
        tag_schema = os.environ.get("SNOWFLAKE_TAG_SCHEMA", "public")

        session = self.manager.session_factory().session

        try:
            session.use_database(tag_database)
            session.use_schema(tag_schema)
        except (NotFoundError, UnauthorizedError):
            raise CustodianError(
                f"Unable to use tag database:{tag_database}, schema:{tag_schema}"
            )

        tags = self.data.get('tags')

        system_tags = self.fetch_system_tags(session, tag_database, tag_schema)
        missing_tags = self.get_missing_tags(system_tags, set([x.lower() for x in tags.keys()]))

        if self.data.get("create_tags_in_system", False):
            for missing_tag in missing_tags:
                self.create_system_tag(session, missing_tag)

        for r in resources:
            self.tag_resource(session, r, tags)
