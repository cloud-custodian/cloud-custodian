# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query
from c7n.utils import local_session


class DescribeDevOpsAgentSpace(query.DescribeSource):
    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('devops-agent')

        def _augment(r):
            r['agentSpaceArn'] = self.manager.generate_arn('agentspace/' + r['agentSpaceId'])
            tags = self.manager.retry(
                client.list_tags_for_resource,
                resourceArn=r['agentSpaceArn'],
            ).get('tags', {})
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in tags.items()]
            return r

        resources = super().augment(resources)
        return list(map(_augment, resources))


@resources.register('devops-agent-space')
class DevOpsAgentSpace(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = 'devops-agent'
        arn_service = 'aidevops'
        enum_spec = ('list_agent_spaces', 'agentSpaces[]', None)
        id = 'agentSpaceId'
        name = 'name'
        arn = 'agentSpaceArn'
        cfn_type = 'AWS::DevOpsAgent::AgentSpace'
        permissions = 'devops-agent:ListAgentSpaces'

    source_mapping = {'describe': DescribeDevOpsAgentSpace, 'config': query.ConfigSource}
