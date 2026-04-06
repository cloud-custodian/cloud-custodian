# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.filters.core import Filter, OPERATORS
from c7n.tags import TagActionFilter, TagDelayedAction, Tag, RemoveTag
from c7n.utils import local_session, type_schema
from c7n import actions as base_actions


# ---------------------------------------------------------------------------
# Describe source with tag augmentation
# ---------------------------------------------------------------------------

class DevOpsAgentSpaceDescribe(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client("devops-agent")

        def _augment(r):
            tags = self.manager.retry(
                client.list_tags_for_resource,
                resourceArn=r["agentSpaceArn"],
            ).get("tags", {})
            r["Tags"] = [{"Key": k, "Value": v} for k, v in tags.items()]
            return r

        return list(map(_augment, resources))


# ---------------------------------------------------------------------------
# Resource manager
# ---------------------------------------------------------------------------

@resources.register("devops-agent-space")
class DevOpsAgentSpace(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "devops-agent"
        enum_spec = ("list_agent_spaces", "agentSpaces[]", None)
        id = #Need to figure out
        name = #Need to figure out
        arn = #Need to figure out
        cfn_type = #Need to figure out

    source_mapping = {"describe": DevOpsAgentSpaceDescribe}

