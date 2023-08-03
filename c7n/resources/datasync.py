# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("aws.datasync-location")
class DataSyncLocation(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "datasync"
        enum_spec = ('list_locations', 'Locations', None)
        arn_type = "location"
        arn = "LocationArn"
        cfn_type = "AWS::DataSync::LocationS3"
        config_type = "AWS::DataSync::LocationS3"
        universal_taggable = object()

    source_mapping = {
       "describe": query.DescribeWithResourceTags,
       "config": query.ConfigSource
    }



@resources.register("aws.datasync-agent")
class DataSyncAgent(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "datasync"
        enum_spec = ('list_agents', 'Agents', None)
        detail_spec = ('describe_agent', 'AgentArn', 'AgentArn', '')
        arn_type = "agent"
        arn = "AgentArn"
        id = "AgentArn"
        name = "Name"
        cfn_type = "AWS::DataSync::Agent"
        universal_taggable = object()

    source_mapping = {
       "describe": query.DescribeWithResourceTags,
    }



@resources.register("aws.datasync-task")
class DataSyncTask(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "datasync"
        enum_spec = ('list_tasks', 'Tasks', None)
        detail_spec = ('describe_task', 'TaskArn', 'TaskArn', '')
        arn_type = "task"
        arn = "TaskArn"
        id = "TaskArn"
        name = "Name"
        cfn_type = "AWS::DataSync::Task"
        config_type = "AWS::DataSync::Task"
        universal_taggable = object()

    source_mapping = {
       "describe": query.DescribeWithResourceTags,
       "config": query.ConfigSource
    }
