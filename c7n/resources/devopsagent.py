# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register('devops-agent-space')
class DevOpsAgentSpace(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = 'devops-agent'
        arn_service = 'aidevops'
        enum_spec = ('list_agent_spaces', 'agentSpaces[]', None)
        id = 'agentSpaceId'
        name = 'name'
        arn_type = 'agentspace'
        permission_prefix = 'aidevops'
        cfn_type = 'AWS::DevOpsAgent::AgentSpace'
        permissions = 'aidevops:ListAgentSpaces'

    source_mapping = {'describe': query.DescribeWithResourceTags, 'config': query.ConfigSource}
