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


@resources.register('sagemaker-notebook')
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

    filters = FilterRegistry('sagemaker-notebook.filters')
    filters.register('marked-for-op', TagActionFilter)
    filter_registry = filters
    permissions = ('sagemaker:ListTags',)

    def augment(self, resources):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(r):
            # List tags for the Notebook-Instance & set as attribute
            tags = client.list_tags(
                ResourceArn=r['NotebookInstanceArn'])['Tags']
            r['Tags'] = tags
            return r

        # Describe notebook-instance & then list tags
        resources = super(NotebookInstance, self).augment(resources)
        with self.executor_factory(max_workers=1) as w:
            return list(filter(None, w.map(_augment, resources)))


@resources.register('sagemaker-job')
class SagemakerJob(QueryResourceManager):

    class resource_type(object):
        service = 'sagemaker'
        enum_spec = ('list_training_jobs', 'TrainingJobSummaries', None)
        detail_spec = (
            'describe_training_job', 'TrainingJobName',
            'TrainingJobName', None)
        id = 'TrainingJobArn'
        name = 'TrainingJobName'
        date = 'CreationTime'
        dimension = None
        filter_name = None


@resources.register('sagemaker-endpoint')
class SagemakerEndpoint(QueryResourceManager):

    class resource_type(object):
        service = 'sagemaker'
        enum_spec = ('list_endpoints', 'Endpoints', None)
        detail_spec = (
            'describe_endpoint', 'EndpointName',
            'EndpointName', None)
        id = 'EndpointArn'
        name = 'EndpointName'
        date = 'CreationTime'
        dimension = None
        filter_name = None

    filters = FilterRegistry('sagemaker-endpoint.filters')
    filters.register('marked-for-op', TagActionFilter)
    filter_registry = filters
    permissions = ('sagemaker:ListTags',)

    def augment(self, endpoints):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(e):
            tags = client.list_tags(
                ResourceArn=e['EndpointArn'])['Tags']
            e['Tags'] = tags
            return e

        # Describe endpoints & then list tags
        endpoints = super(SagemakerEndpoint, self).augment(endpoints)
        with self.executor_factory(max_workers=1) as w:
            return list(filter(None, w.map(_augment, endpoints)))


@resources.register('sagemaker-endpoint-config')
class SagemakerEndpointConfig(QueryResourceManager):

    class resource_type(object):
        service = 'sagemaker'
        enum_spec = ('list_endpoint_configs', 'EndpointConfigs', None)
        detail_spec = (
            'describe_endpoint_config', 'EndpointConfigName',
            'EndpointConfigName', None)
        id = 'EndpointConfigArn'
        name = 'EndpointConfigName'
        date = 'CreationTime'
        dimension = None
        filter_name = None

    filters = FilterRegistry('sagemaker-endpoint-config.filters')
    filters.register('marked-for-op', TagActionFilter)
    filter_registry = filters
    permissions = ('sagemaker:ListTags',)

    def augment(self, endpoints):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(e):
            tags = client.list_tags(
                ResourceArn=e['EndpointConfigArn'])['Tags']
            e['Tags'] = tags
            return e

        endpoints = super(SagemakerEndpointConfig, self).augment(endpoints)
        with self.executor_factory(max_workers=1) as w:
            return list(filter(None, w.map(_augment, endpoints)))


class StateTransitionFilter(object):
    """Filter instances by state.

    Try to simplify construction for policy authors by automatically
    filtering elements (filters or actions) to the instances states
    they are valid for.

    """
    valid_origin_states = ()

    def filter_instance_state(self, instances, states=None):
        states = states or self.valid_origin_states
        orig_length = len(instances)
        results = [i for i in instances
                   if i['NotebookInstanceStatus'] in states]
        self.log.info("%s %d of %d notebook instances" % (
            self.__class__.__name__, len(results), orig_length))
        return results


@SagemakerEndpoint.action_registry.register('tag')
@SagemakerEndpointConfig.action_registry.register('tag')
@NotebookInstance.action_registry.register('tag')
class TagNotebookInstance(Tag):
    """Action to create tag(s) on a SageMaker resource
    (notebook-instance, endpoint, endpoint-config)

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-sagemaker-notebook
                resource: sagemaker-notebook
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-value

              - name: tag-sagemaker-endpoint
                resource: sagemaker-endpoint
                filters:
                    - "tag:required-tag": absent
                actions:
                  - type: tag
                    key: required-tag
                    value: required-value

              - name: tag-sagemaker-endpoint-config
                resource: sagemaker-endpoint-config
                filters:
                    - "tag:required-tag": absent
                actions:
                  - type: tag
                    key: required-tag
                    value: required-value
    """
    permissions = ('sagemaker:AddTags',)

    def process_resource_set(self, resources, tags):
        client = local_session(
            self.manager.session_factory).client('sagemaker')

        tag_list = []
        for t in tags:
            tag_list.append({'Key': t['Key'], 'Value': t['Value']})
        for r in resources:
            client.add_tags(ResourceArn=r[self.id_key], Tags=tag_list)


@SagemakerEndpoint.action_registry.register('remove-tag')
@SagemakerEndpointConfig.action_registry.register('remove-tag')
@NotebookInstance.action_registry.register('remove-tag')
class RemoveTagNotebookInstance(RemoveTag):
    """Remove tag(s) from SageMaker resources
    (notebook-instance, endpoint, endpoint-config)

    :example:

    .. code-block:: yaml

            policies:
              - name: sagemaker-notebook-remove-tag
                resource: sagemaker-notebook
                filters:
                  - "tag:BadTag": present
                actions:
                  - type: remove-tag
                    tags: ["BadTag"]

              - name: sagemaker-endpoint-remove-tag
                resource: sagemaker-endpoint
                filters:
                  - "tag:expired-tag": present
                actions:
                  - type: remove-tag
                    tags: ["expired-tag"]

              - name: sagemaker-endpoint-config-remove-tag
                resource: sagemaker-endpoint-config
                filters:
                  - "tag:expired-tag": present
                actions:
                  - type: remove-tag
                    tags: ["expired-tag"]
    """
    permissions = ('sagemaker:DeleteTags',)

    def process_resource_set(self, resources, keys):
        client = local_session(
            self.manager.session_factory).client('sagemaker')

        for r in resources:
            client.delete_tags(ResourceArn=r[self.id_key], TagKeys=keys)


@SagemakerEndpoint.action_registry.register('mark-for-op')
@SagemakerEndpointConfig.action_registry.register('mark-for-op')
@NotebookInstance.action_registry.register('mark-for-op')
class MarkNotebookInstanceForOp(TagDelayedAction):
    """Mark SageMaker resources for deferred action
    (notebook-instance, endpoint, endpoint-config)

    :example:

    .. code-block:: yaml

        policies:
          - name: sagemaker-notebook-invalid-tag-stop
            resource: sagemaker-notebook
            filters:
              - "tag:InvalidTag": present
            actions:
              - type: mark-for-op
                op: stop
                days: 1

          - name: sagemaker-endpoint-failure-delete
            resource: sagemaker-endpoint
            filters:
              - 'EndpointStatus': 'Failed'
            actions:
              - type: mark-for-op
                op: delete
                days: 1

          - name: sagemaker-endpoint-config-invalid-size-delete
            resource: sagemaker-notebook
            filters:
              - type: value
              - key: ProductionVariants[].InstanceType
              - value: 'ml.m4.10xlarge'
              - op: contains
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """
    permissions = ('sagemaker:AddTags',)

    def process_resource_set(self, resources, tags):
        client = local_session(
            self.manager.session_factory).client('sagemaker')

        tag_list = []
        for t in tags:
            tag_list.append({'Key': t['Key'], 'Value': t['Value']})

        for r in resources:
            client.add_tags(ResourceArn=r[self.id_key], Tags=tag_list)


@NotebookInstance.action_registry.register('start')
class StartNotebookInstance(BaseAction, StateTransitionFilter):
    """Start sagemaker-notebook(s)

    :example:

    .. code-block: yaml

        policies:
          - name: start-sagemaker-notebook
            resource: sagemaker-notebook
            actions:
              - start
    """
    schema = type_schema('start')
    permissions = ('sagemaker:StartNotebookInstance',)
    valid_origin_states = ('Stopped',)

    def process_instance(self, resource):
        client = local_session(
            self.manager.session_factory).client('sagemaker')
        client.start_notebook_instance(
            NotebookInstanceName=resource['NotebookInstanceName'])

    def process(self, resources):
        resources = self.filter_instance_state(resources)
        if not len(resources):
            return

        with self.executor_factory(max_workers=2) as w:
                list(w.map(self.process_instance, resources))


@NotebookInstance.action_registry.register('stop')
class StopNotebookInstance(BaseAction, StateTransitionFilter):
    """Stop sagemaker-notebook(s)

    :example:

    .. code-block: yaml

        policies:
          - name: stop-sagemaker-notebook
            resource: sagemaker-notebook
            filters:
              - "tag:DeleteMe": present
            actions:
              - stop
    """
    schema = type_schema('stop')
    permissions = ('sagemaker:StopNotebookInstance',)
    valid_origin_states = ('InService',)

    def process_instance(self, resource):
        client = local_session(
            self.manager.session_factory).client('sagemaker')
        client.stop_notebook_instance(
            NotebookInstanceName=resource['NotebookInstanceName'])

    def process(self, resources):
        resources = self.filter_instance_state(resources)
        if not len(resources):
            return

        with self.executor_factory(max_workers=2) as w:
                list(w.map(self.process_instance, resources))


@NotebookInstance.action_registry.register('delete')
class DeleteNotebookInstance(BaseAction, StateTransitionFilter):
    """Deletes sagemaker-notebook(s)

    :example:

    .. code-block: yaml

        policies:
          - name: delete-sagemaker-notebook
            resource: sagemaker-notebook
            filters:
              - "tag:DeleteMe": present
            actions:
              - delete
    """
    schema = type_schema('delete')
    permissions = ('sagemaker:DeleteNotebookInstance',)
    valid_origin_states = ('Stopped', 'Failed',)

    def process_instance(self, resource):
        client = local_session(
            self.manager.session_factory).client('sagemaker')
        client.delete_notebook_instance(
            NotebookInstanceName=resource['NotebookInstanceName'])

    def process(self, resources):
        resources = self.filter_instance_state(resources)
        if not len(resources):
            return

        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_instance, resources))


@SagemakerJob.action_registry.register('stop')
class SagemakerJobStop(BaseAction):
    """Stops a SageMaker job

    :example:

    .. code-block: yaml

        policies:
          - name: stop-ml-job
            resource: sagemaker-job
            filters:
              - TrainingJobName: ml-job-10
            actions:
              - stop
    """
    schema = type_schema('stop')
    permissions = ('sagemaker:StopTrainingJob',)

    def process_job(self, job):
        client = local_session(
            self.manager.session_factory).client('sagemaker')
        try:
            client.stop_training_job(
                TrainingJobName=job['TrainingJobName'])
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFound':
                self.log.exception(
                    "Exception stopping sagemaker job %s:\n %s" % (
                        job['TrainingJobName'], e))
            else:
                raise

    def process(self, jobs):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_job, jobs))


@SagemakerEndpoint.action_registry.register('delete')
class SagemakerEndpointDelete(BaseAction):
    """Delete a SageMaker endpoint

    :example:

    .. code-block: yaml

        policies:
          - name: delete-sagemaker-endpoint
            resource: sagemaker-endpoint
            filters:
              - EndpointName: sagemaker-ep--2018-01-01-00-00-00
            actions:
              - type: delete
    """
    permissions = (
        'sagemaker:DeleteEndpoint', 'sagemaker:DeleteEndpointConfig')
    schema = type_schema('delete')

    def process_endpoint(self, endpoint):
        client = local_session(
            self.manager.session_factory).client('sagemaker')
        client.delete_endpoint(EndpointName=endpoint['EndpointName'])

    def process(self, endpoints):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_endpoint, endpoints))


@SagemakerEndpointConfig.action_registry.register('delete')
class SagemakerEndpointConfigDelete(BaseAction):
    """Delete a SageMaker endpoint

    :example:

    .. code-block: yaml

        policies:
          - name: delete-sagemaker-endpoint-config
            resource: sagemaker-endpoint-config
            filters:
              - EndpointConfigName: sagemaker-2018-01-01-00-00-00-T00
            actions:
              - delete
    """
    schema = type_schema('delete')
    permissions = ('sagemaker:DeleteEndpointConfig',)

    def process_endpoint_config(self, endpoint):
        client = local_session(
            self.manager.session_factory).client('sagemaker')
        client.delete_endpoint_config(
            EndpointConfigName=endpoint['EndpointConfigName'])

    def process(self, endpoints):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_endpoint_config, endpoints))
