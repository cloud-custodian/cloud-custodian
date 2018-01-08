# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from botocore.exceptions import ClientError

from c7n.manager import resources
from c7n.filters import FilterRegistry
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema
from c7n.actions import BaseAction
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction

filters = FilterRegistry('sagemaker.filters')
filters.register('marked-for-op', TagActionFilter)


@resources.register('notebook-instance')
class NotebookInstance(QueryResourceManager):

    class resource_type(object):
        service = 'sagemaker'
        enum_spec = ('list_notebook_instances', 'NotebookInstances', None)
        detail_spec = (
            'describe_notebook_instance', 'NotebookInstanceName',
            'NotebookInstanceName', None)
        id = 'NotebookInstanceArn'
        name = 'NotebookInstanceName'
        date = 'CreationTime'
        dimension = None
        filter_name = None

    filter_registry = filters
    permissions = ('sagemaker:ListTags',)

    def augment(self, resources):
        def _tags(r):
            client = local_session(self.session_factory).client('sagemaker')
            tags = client.list_tags(
                ResourceArn=r['NotebookInstanceArn'])['Tags']
            r.setdefault('Tags', []).extend(tags)
            return r

        with self.executor_factory(max_workers=2) as w:
            return list(filter(None, w.map(_tags, resources)))


@NotebookInstance.action_registry.register('tag')
class TagNotebookInstance(Tag):
    """Action to create tag(s) on a notebook-instance

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-notebook-instance
                resource: notebook-instance
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-value
    """
    permissions = ('sagemaker:AddTags',)

    def process_resource_set(self, resources, tags):
        client = local_session(
            self.manager.session_factory).client('sagemaker')

        tag_list = []
        for t in tags:
            tag_list.append({'Key': t['Key'], 'Value': t['Value']})

        for r in resources:
            try:
                client.add_tags(
                    ResourceArn=r['NotebookInstanceArn'],
                    Tags=tag_list)
            except ClientError as e:
                self.log.exception(
                    'Exception tagging notebook instance %s: %s',
                    r['NotebookInstanceName'], e)


@NotebookInstance.action_registry.register('remove-tag')
class RemoveTagNotebookInstance(RemoveTag):
    """Remove tag(s) from notebook-instance(s)
    
    :example:

    .. code-block:: yaml

            policies:
              - name: notebook-instance-remove-tag
                resource: notebook-instabce
                filters:
                  - "tag:BadTag": present
                actions:
                  - type: remove-tag
                    tags: ["BadTag"]
    """
    permissions = ('sagemaker:DeleteTags',)

    def process_resource_set(self, resources, keys):
        client = local_session(
            self.manager.session_factory).client('sagemaker')

        for r in resources:
            try:
                client.delete_tags(
                    ResourceArn=r['NotebookInstanceArn'],
                    TagKeys=keys)
            except ClientError as e:
                self.log.exception(
                    'Exception tagging notebook instance %s: %s',
                    r['NotebookInstanceName'], e)


@NotebookInstance.action_registry.register('mark-for-op')
class MarkNotebookInstanceForOp(TagDelayedAction):
    """Mark notebook instance for deferred action
    
    :example:
    
    .. code-block:: yaml

        policies:
          - name: notebook-instance-invalid-tag-delete
            resource: notebook-instance
            filters:
              - "tag:InvalidTag": present
            actions:
              - type: mark-for-op
                op: stop
                days: 7
    """
    permissions = ('sagemaker:AddTags',)

    def process_resource_set(self, resources, tags):
        client = local_session(
            self.manager.session_factory).client('sagemaker')

        tag_list = []
        for t in tags:
            tag_list.append({'Key': t['Key'], 'Value': t['Value']})

        for r in resources:
            try:
                client.add_tags(
                    ResourceArn=r['NotebookInstanceArn'],
                    Tags=tag_list)
            except ClientError as e:
                self.log.exception(
                    'Exception tagging notebook instance %s: %s',
                    r['NotebookInstanceName'], e)


@NotebookInstance.action_registry.register('stop')
class StopNotebookInstance(BaseAction):
    """Stop notebook-instance(s)
    
    :example:
    
    .. code-block: yaml
    
        policies:
          - name: stop-notebook-instance
            resource: notebook-instance
            filters:
              - "tag:DeleteMe": present
              - NotebookInstanceStatus: InService
            actions:
              - stop
    """
    schema = type_schema('stop')
    permissions = ('sagemaker:StopNotebookInstance',)

    def process_instance(self, resource):
        client = local_session(
            self.manager.session_factory).client('sagemaker')
        try:
            client.stop_notebook_instance(
                NotebookInstanceName=resource['NotebookInstanceName'])
        except ClientError as e:
            self.log.exception(
                "Exception stopping notebook instance %s:\n %s" % (
                    resource['NotebookInstanceName'], e))

    def process(self, resources):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_instance, resources))


@NotebookInstance.action_registry.register('delete')
class DeleteNotebookInstance(BaseAction):
    """Deletes notebook-instance(s)

    :example:

    .. code-block: yaml
    
        policies:
          - name: delete-notebook-instance
            resource: notebook-instance
            filters:
              - "tag:DeleteMe": present
              - NotebookInstanceStatus: Stopped
            actions:
              - delete
    """
    schema = type_schema('delete')
    permissions = ('sagemaker:DeleteNotebookInstance',)

    def process_instance(self, resource):
        client = local_session(
            self.manager.session_factory).client('sagemaker')
        try:
            client.delete_notebook_instance(
                NotebookInstanceName=resource['NotebookInstanceName'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting notebook instance %s:\n %s" % (
                    resource['NotebookInstanceName'], e))

    def process(self, resources):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_instance, resources))
