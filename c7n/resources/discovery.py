# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("aws.appdiscovery-agent")
class AppdiscoveryAgent(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "discovery"
        enum_spec = ('describe_agents', 'agentsInfo', None)
        arn = False
        id = "agentId"
        name = "hostName"



@resources.register("aws.appdiscovery")
class Appdiscovery(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "discovery"
        enum_spec = ('list_configurations', 'configurations', None)
        detail_spec = (
            'describe_configurations',
            'configurationIds',
            'configurationId',
            'configurations'
        )
        arn = False
        id = "configurationId"
        name = "name"

