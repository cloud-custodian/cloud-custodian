# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, ConfigSource, DescribeSource
from c7n.tags import Tag, RemoveTag, TagDelayedAction, TagActionFilter
from c7n.utils import type_schema, local_session, get_partition


class ExperimentTemplateDescribe(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        # tag normalize for value filter
        for r in resources:
            if 'tags' not in r:
                continue
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in r.pop('tags', {}).items()]
        return resources


@resources.register('fis-template')
class ExperimentTemplate(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'fis'
        enum_spec = ('list_experiment_templates', 'experimentTemplates', None)
        detail_spec = ('get_experiment_template', 'id', 'id', 'experimentTemplate')
        name = id = 'id'
        date = 'creationTime'
        config_type = cfn_type = "AWS::FIS::ExperimentTemplate"
        arn_type = 'experiment-template'

    source_mapping = {'describe': ExperimentTemplateDescribe,
                      'config': ConfigSource}

    def get_arns(self, resources):
        partition = get_partition(self.region)
        return [
            "arn:%s:fis:%s:%s:experiment-template/%s"
            % (partition, self.region, self.account_id, r['id'])
            for r in resources
        ]


@ExperimentTemplate.action_registry.register('tag')
class TagExperiment(Tag):
    permissions = ('fis:TagResource',)

    def process_resource_set(self, client, resource_set, tags):
        ptags = {t['Key']: t['Value'] for t in tags}
        for arn in self.manager.get_arns(resource_set):
            self.manager.retry(client.tag_resource, resourceArn=arn, tags=ptags)


@ExperimentTemplate.action_registry.register('mark-for-op', TagDelayedAction)
@ExperimentTemplate.filter_registry.register('marked-for-op', TagActionFilter)
class MarkForOp(TagDelayedAction):
    """Action to create a delayed action on fis-template to start at a later date

    .. code-block:: yaml

        policies:
            - name: mark-for-delete
              resource: "aws.fis-template"
              actions:
                - type: mark-for-op
                  op: tag
                  days: 1
    """


@ExperimentTemplate.action_registry.register('remove-tag')
class RemoveExperimentTag(RemoveTag):
    permissions = ('fis:UntagResource',)

    def process_resource_set(self, client, resource_set, tags):
        for arn in self.manager.get_arns(resource_set):
            self.manager.retry(client.untag_resource, resourceArn=arn, tagKeys=tags)


@ExperimentTemplate.action_registry.register('delete')
class Delete(Action):
    permissions = ('fis:DeleteExperimentTemplate',)
    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('fis')
        for r in resources:
            self.manager.retry(client.delete_experiment_template, id=r['id'])


class ExperimentDescribe(DescribeSource):
    def augment(self, resources):
        resources = super().augment(resources)
        for r in resources:
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in r.pop('tags', {}).items()]
        return resources


@resources.register('fis-experiment')
class Experiment(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'fis'
        enum_spec = ('list_experiments', 'experiments', None)
        detail_spec = ('get_experiment', 'id', 'id', 'experiment')
        name = id = 'id'
        date = 'creationTime'
        arn_type = 'experiment'

    source_mapping = {'describe': ExperimentDescribe}

    def get_arns(self, resources):
        partition = get_partition(self.region)
        return [
            "arn:%s:fis:%s:%s:experiment/%s"
            % (partition, self.region, self.account_id, r['id'])
            for r in resources
        ]


@Experiment.action_registry.register('tag')
class TagExperiments(Tag):
    permissions = ('fis:TagResource',)

    def process_resource_set(self, client, resource_set, tags):
        ptags = {t['Key']: t['Value'] for t in tags}
        for arn in self.manager.get_arns(resource_set):
            self.manager.retry(client.tag_resource, resourceArn=arn, tags=ptags)


@Experiment.action_registry.register('remove-tag')
class RemoveTagExperiments(RemoveTag):
    permissions = ('fis:UntagResource',)

    def process_resource_set(self, client, resource_set, tags):
        for arn in self.manager.get_arns(resource_set):
            self.manager.retry(client.untag_resource, resourceArn=arn, tagKeys=tags)
