# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Data Pipeline
"""
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters import FilterRegistry
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import chunks, local_session, get_retry, type_schema
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction


filters = FilterRegistry('datapipeline.filters')
filters.register('marked-for-op', TagActionFilter)


@resources.register('datapipeline')
class DataPipeline(QueryResourceManager):

    retry = staticmethod(get_retry(('Throttled',)))

    filter_registry = filters

    class resource_type(TypeInfo):
        service = 'datapipeline'
        arn_type = 'dataPipeline'
        id = 'id'
        name = 'name'
        dimension = 'name'
        batch_detail_spec = (
            'describe_pipelines', 'pipelineIds', 'id', 'pipelineDescriptionList', None)
        enum_spec = ('list_pipelines', 'pipelineIdList', None)

    def augment(self, resources):
        filter(None, _datapipeline_info(
            resources, self.session_factory, self.executor_factory,
            self.retry))
        return resources


def _datapipeline_info(pipes, session_factory, executor_factory, retry):

    client = local_session(session_factory).client('datapipeline')

    def process_tags(pipe_set):
        pipe_map = {pipe['id']: pipe for pipe in pipe_set}

        while True:
            try:
                results = retry(
                    client.describe_pipelines,
                    pipelineIds=list(pipe_map.keys()))
                break
            except ClientError as e:
                if e.response['Error']['Code'] != 'PipelineNotFound':
                    raise
                msg = e.response['Error']['Message']
                _, lb_name = msg.strip().rsplit(' ', 1)
                pipe_map.pop(lb_name)
                if not pipe_map:
                    results = {'TagDescriptions': []}
                    break
                continue

        for pipe_desc in results['pipelineDescriptionList']:
            pipe = pipe_map[pipe_desc['pipelineId']]
            pipe['Tags'] = [
                {'Key': t['key'], 'Value': t['value']}
                for t in pipe_desc['tags']]
            for field in pipe_desc['fields']:
                key = field['key']
                if not key.startswith('@'):
                    continue
                pipe[key[1:]] = field['stringValue']

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, chunks(pipes, 20)))


@DataPipeline.action_registry.register('delete')
class Delete(BaseAction):
    """Action to delete DataPipeline

    It is recommended to use a filter to avoid unwanted deletion of DataPipeline

    :example:

    .. code-block:: yaml

            policies:
              - name: datapipeline-delete
                resource: datapipeline
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("datapipeline:DeletePipeline",)

    def process(self, pipelines):
        client = local_session(
            self.manager.session_factory).client('datapipeline')

        for p in pipelines:
            try:
                client.delete_pipeline(pipelineId=p['id'])
            except client.exceptions.PipelineNotFoundException:
                continue


@DataPipeline.action_registry.register('mark-for-op')
class MarkForOpPipeline(TagDelayedAction):
    """Action to specify an action to occur at a later date

    :example:

    .. code-block:: yaml

            policies:
              - name: pipeline-delete-unused
                resource: datapipeline
                filters:
                  - "tag:custodian_cleanup": absent
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    msg: "Unused data pipeline: {op}@{action_date}"
                    op: delete
                    days: 7
    """


@DataPipeline.action_registry.register('tag')
class TagPipeline(Tag):
    """Action to create tag(s) on a pipeline

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-pipeline
                resource: datapipeline
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """

    permissions = ('datapipeline:AddTags',)

    def process_resource_set(self, client, pipelines, tags):
        tag_array = [dict(key=t['Key'], value=t['Value']) for t in tags]
        for pipeline in pipelines:
            try:
                client.add_tags(pipelineId=pipeline['id'], tags=tag_array)
            except (client.exceptions.PipelineDeletedException,
                    client.exceptions.PipelineNotFoundException):
                continue


@DataPipeline.action_registry.register('remove-tag')
class UntagPipeline(RemoveTag):
    """Action to remove tag(s) on a pipeline

    :example:

    .. code-block:: yaml

            policies:
              - name: pipeline-remove-tag
                resource: datapipeline
                filters:
                  - "tag:OutdatedTag": present
                actions:
                  - type: remove-tag
                    tags: ["OutdatedTag"]
    """

    permissions = ('datapipeline:RemoveTags',)

    def process_resource_set(self, client, pipelines, tags):
        for pipeline in pipelines:
            try:
                client.remove_tags(pipelineId=pipeline['id'], tagKeys=tags)
            except (client.exceptions.PipelineDeletedException,
                    client.exceptions.PipelineNotFoundException):
                continue
