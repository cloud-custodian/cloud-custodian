# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("appdiscovery-agent")
class AppdiscoveryAgent(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "discovery"
        enum_spec = ('describe_agents', 'agentsInfo', None)
        arn = False
        id = "agentId"
        name = "hostName"
