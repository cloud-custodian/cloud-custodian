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

import six

from c7n.actions import BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import FilterRegistry
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.filters.vpc import SubnetFilter, SecurityGroupFilter


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

    filter_registry = FilterRegistry('sagemaker-notebook.filters')
    filter_registry.register('marked-for-op', TagActionFilter)
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
            'describe_training_job', 'TrainingJobName', 'TrainingJobName', None)
        id = 'TrainingJobArn'
        name = 'TrainingJobName'
        date = 'CreationTime'
        dimension = None
        filter_name = None

    permissions = (
        'sagemaker:ListTrainingJobs', 'sagemaker:DescribeTrainingJobs',
        'sagemaker:ListTags')

    def __init__(self, ctx, data):
        super(SagemakerJob, self).__init__(ctx, data)
        self.queries = QueryFilter.parse(
            self.data.get('query', [
                {'StatusEquals': 'InProgress'}]))

    def resources(self, query=None):
        for q in self.queries:
            if q is None:
                continue
            query = query or {}
            for k, v in q.items():
                query[k] = v
            return super(SagemakerJob, self).resources(query=query)

    def augment(self, jobs):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(j):
            tags = client.list_tags(ResourceArn=j['TrainingJobArn'])['Tags']
            j['Tags'] = tags
            return j

        jobs = super(SagemakerJob, self).augment(jobs)
        with self.executor_factory(max_workers=1) as w:
            return list(filter(None, w.map(_augment, jobs)))


JOB_FILTERS = ('StatusEquals', 'NameContains',)


class QueryFilter(object):
    @classmethod
    def parse(cls, data):
        results = []
        names = set()
        for d in data:
            if not isinstance(d, dict):
                raise PolicyValidationError(
                    "Training-Job Query Filter Invalid structure %s" % d)
            for k, v in d.items():
                if isinstance(v, list):
                    raise ValueError(
                        'Training-job query filter invalid structure %s' % v)
            query = cls(d).validate().query()
            if query['Name'] in names:
                # Cannot filter multiple times on the same key
                continue
            names.add(query['Name'])
            if isinstance(query['Value'], list):
                results.append({query['Name']: query['Value'][0]})
                continue
            results.append({query['Name']: query['Value']})
        if 'StatusEquals' not in names:
            # add default StatusEquals if not included
            results.append({'Name': 'StatusEquals', 'Value': 'InProgress'})
        return results

    def __init__(self, data):
        self.data = data
        self.key = None
        self.value = None

    def validate(self):
        if not len(list(self.data.keys())) == 1:
            raise PolicyValidationError(
                "Training-Job Query Filter Invalid %s" % self.data)
        self.key = list(self.data.keys())[0]
        self.value = list(self.data.values())[0]

        if self.key not in JOB_FILTERS and not self.key.startswith('tag:'):
            raise PolicyValidationError(
                "Training-Job Query Filter invalid filter name %s" % (
                    self.data))

        if self.value is None:
            raise PolicyValidationError(
                "Training-Job Query Filters must have a value, use tag-key"
                " w/ tag name as value for tag present checks"
                " %s" % self.data)
        return self

    def query(self):
        value = self.value
        if isinstance(self.value, six.string_types):
            value = [self.value]
        return {'Name': self.key, 'Value': value}


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

    filter_registry = FilterRegistry('sagemaker-endpoint.filters')
    filter_registry.register('marked-for-op', TagActionFilter)
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

    filter_registry = FilterRegistry('sagemaker-endpoint-config.filters')
    filter_registry.register('marked-for-op', TagActionFilter)
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


@resources.register('sagemaker-model')
class Model(QueryResourceManager):
    class resource_type(object):
        service = 'sagemaker'
        enum_spec = ('list_models', 'Models', None)
        detail_spec = (
            'describe_model', 'ModelName',
            'ModelName', None)
        id = 'ModelArn'
        name = 'ModelName'
        date = 'CreationTime'
        dimension = None
        filter_name = None

    filter_registry = FilterRegistry('sagemaker-model.filters')
    filter_registry.register('marked-for-op', TagActionFilter)
    permissions = ('sagemaker:ListTags',)

    def augment(self, resources):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(r):
            tags = client.list_tags(
                ResourceArn=r['ModelArn'])['Tags']
            r.setdefault('Tags', []).extend(tags)
            return r

        with self.executor_factory(max_workers=1) as w:
            return list(filter(None, w.map(_augment, resources)))


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
@SagemakerJob.action_registry.register('tag')
@Model.action_registry.register('tag')
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

              - name: tag-sagemaker-job
                resource: sagemaker-job
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
@SagemakerJob.action_registry.register('remove-tag')
@Model.action_registry.register('remove-tag')
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

              - name: sagemaker-job-remove-tag
                resource: sagemaker-job
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
@Model.action_registry.register('mark-for-op')
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


@NotebookInstance.filter_registry.register('security-group')
class NotebookSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[]"


@NotebookInstance.filter_registry.register('subnet')
class NotebookSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "SubnetId"


@Model.action_registry.register('delete')
class DeleteModel(BaseAction, StateTransitionFilter):
    """Deletes sagemaker-model(s)

    :example:

    .. code-block: yaml

        policies:
          - name: delete-sagemaker-model
            resource: sagemaker-model
            filters:
              - "tag:DeleteMe": present
            actions:
              - delete
    """
    schema = type_schema('delete')
    permissions = ('sagemaker:DeleteModel',)

    def process_instance(self, resource):
        client = local_session(
            self.manager.session_factory).client('sagemaker')
        client.delete_model(
            ModelName=resource['ModelName'])

    def process(self, resources):
        if not len(resources):
            return

        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_instance, resources))


@SagemakerJob.action_registry.register('stop')
class SagemakerJobStop(BaseAction):
    """Stops a SageMaker job

    :example:

    .. code-block:: yaml

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
