# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions import BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.utils import local_session, type_schema
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.filters.vpc import SubnetFilter, SecurityGroupFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters.offhours import OffHour, OnHour


@resources.register('sagemaker-notebook')
class NotebookInstance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_notebook_instances', 'NotebookInstances', None)
        detail_spec = (
            'describe_notebook_instance', 'NotebookInstanceName',
            'NotebookInstanceName', None)
        arn = id = 'NotebookInstanceArn'
        name = 'NotebookInstanceName'
        date = 'CreationTime'
        cfn_type = 'AWS::SageMaker::NotebookInstance'

    permissions = ('sagemaker:ListTags',)

    def augment(self, resources):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(r):
            # List tags for the Notebook-Instance & set as attribute
            tags = self.retry(client.list_tags,
                ResourceArn=r['NotebookInstanceArn'])['Tags']
            r['Tags'] = tags
            return r

        # Describe notebook-instance & then list tags
        resources = super(NotebookInstance, self).augment(resources)
        return list(map(_augment, resources))


NotebookInstance.filter_registry.register('marked-for-op', TagActionFilter)
NotebookInstance.filter_registry.register('offhour', OffHour)
NotebookInstance.filter_registry.register('onhour', OnHour)


@resources.register('sagemaker-job')
class SagemakerJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_training_jobs', 'TrainingJobSummaries', None)
        detail_spec = (
            'describe_training_job', 'TrainingJobName', 'TrainingJobName', None)
        arn = id = 'TrainingJobArn'
        name = 'TrainingJobName'
        date = 'CreationTime'
        permission_augment = (
            'sagemaker:DescribeTrainingJob', 'sagemaker:ListTags')

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
            tags = self.retry(client.list_tags,
                ResourceArn=j['TrainingJobArn'])['Tags']
            j['Tags'] = tags
            return j

        jobs = super(SagemakerJob, self).augment(jobs)
        return list(map(_augment, jobs))


@resources.register('sagemaker-transform-job')
class SagemakerTransformJob(QueryResourceManager):

    class resource_type(TypeInfo):
        arn_type = "transform-job"
        service = 'sagemaker'
        enum_spec = ('list_transform_jobs', 'TransformJobSummaries', None)
        detail_spec = (
            'describe_transform_job', 'TransformJobName', 'TransformJobName', None)
        arn = id = 'TransformJobArn'
        name = 'TransformJobName'
        date = 'CreationTime'
        filter_name = 'NameContains'
        filter_type = 'scalar'
        permission_augment = ('sagemaker:DescribeTransformJob', 'sagemaker:ListTags')

    def __init__(self, ctx, data):
        super(SagemakerTransformJob, self).__init__(ctx, data)
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
        return super(SagemakerTransformJob, self).resources(query=query)

    def augment(self, jobs):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(j):
            tags = self.retry(client.list_tags,
                ResourceArn=j['TransformJobArn'])['Tags']
            j['Tags'] = tags
            return j

        return list(map(_augment, super(SagemakerTransformJob, self).augment(jobs)))


class QueryFilter:

    JOB_FILTERS = ('StatusEquals', 'NameContains',)

    @classmethod
    def parse(cls, data):
        results = []
        names = set()
        for d in data:
            if not isinstance(d, dict):
                raise PolicyValidationError(
                    "Job Query Filter Invalid structure %s" % d)
            for k, v in d.items():
                if isinstance(v, list):
                    raise ValueError(
                        'Job query filter invalid structure %s' % v)
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
                "Job Query Filter Invalid %s" % self.data)
        self.key = list(self.data.keys())[0]
        self.value = list(self.data.values())[0]

        if self.key not in self.JOB_FILTERS and not self.key.startswith('tag:'):
            raise PolicyValidationError(
                "Job Query Filter invalid filter name %s" % (
                    self.data))

        if self.value is None:
            raise PolicyValidationError(
                "Job Query Filters must have a value, use tag-key"
                " w/ tag name as value for tag present checks"
                " %s" % self.data)
        return self

    def query(self):
        value = self.value
        if isinstance(self.value, str):
            value = [self.value]
        return {'Name': self.key, 'Value': value}


@resources.register('sagemaker-endpoint')
class SagemakerEndpoint(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_endpoints', 'Endpoints', None)
        detail_spec = (
            'describe_endpoint', 'EndpointName',
            'EndpointName', None)
        arn = id = 'EndpointArn'
        name = 'EndpointName'
        date = 'CreationTime'
        cfn_type = 'AWS::SageMaker::Endpoint'

    permissions = ('sagemaker:ListTags',)

    def augment(self, endpoints):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(e):
            tags = self.retry(client.list_tags,
                ResourceArn=e['EndpointArn'])['Tags']
            e['Tags'] = tags
            return e

        # Describe endpoints & then list tags
        endpoints = super(SagemakerEndpoint, self).augment(endpoints)
        return list(map(_augment, endpoints))


SagemakerEndpoint.filter_registry.register('marked-for-op', TagActionFilter)


@resources.register('sagemaker-endpoint-config')
class SagemakerEndpointConfig(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_endpoint_configs', 'EndpointConfigs', None)
        detail_spec = (
            'describe_endpoint_config', 'EndpointConfigName',
            'EndpointConfigName', None)
        arn = id = 'EndpointConfigArn'
        name = 'EndpointConfigName'
        date = 'CreationTime'
        cfn_type = 'AWS::SageMaker::EndpointConfig'

    permissions = ('sagemaker:ListTags',)

    def augment(self, endpoints):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(e):
            tags = self.retry(client.list_tags,
                ResourceArn=e['EndpointConfigArn'])['Tags']
            e['Tags'] = tags
            return e

        endpoints = super(SagemakerEndpointConfig, self).augment(endpoints)
        return list(map(_augment, endpoints))


SagemakerEndpointConfig.filter_registry.register('marked-for-op', TagActionFilter)


class DescribeModel(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('sagemaker')

        def _augment(r):
            tags = self.manager.retry(client.list_tags,
                ResourceArn=r['ModelArn'])['Tags']
            r.setdefault('Tags', []).extend(tags)
            return r

        resources = super(DescribeModel, self).augment(resources)
        return list(map(_augment, resources))


@resources.register('sagemaker-model')
class Model(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_models', 'Models', None)
        detail_spec = (
            'describe_model', 'ModelName',
            'ModelName', None)
        arn = id = 'ModelArn'
        name = 'ModelName'
        date = 'CreationTime'
        cfn_type = config_type = 'AWS::SageMaker::Model'

    source_mapping = {
        'describe': DescribeModel,
        'config': ConfigSource
    }

    permissions = ('sagemaker:ListTags',)


Model.filter_registry.register('marked-for-op', TagActionFilter)


@SagemakerEndpoint.action_registry.register('tag')
@SagemakerEndpointConfig.action_registry.register('tag')
@NotebookInstance.action_registry.register('tag')
@SagemakerJob.action_registry.register('tag')
@SagemakerTransformJob.action_registry.register('tag')
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

    def process_resource_set(self, client, resources, tags):
        mid = self.manager.resource_type.id
        for r in resources:
            client.add_tags(ResourceArn=r[mid], Tags=tags)


@SagemakerEndpoint.action_registry.register('remove-tag')
@SagemakerEndpointConfig.action_registry.register('remove-tag')
@NotebookInstance.action_registry.register('remove-tag')
@SagemakerJob.action_registry.register('remove-tag')
@SagemakerTransformJob.action_registry.register('remove-tag')
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

    def process_resource_set(self, client, resources, keys):
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


@NotebookInstance.action_registry.register('start')
class StartNotebookInstance(BaseAction):
    """Start sagemaker-notebook(s)

    :example:

    .. code-block:: yaml

        policies:
          - name: start-sagemaker-notebook
            resource: sagemaker-notebook
            actions:
              - start
    """
    schema = type_schema('start')
    permissions = ('sagemaker:StartNotebookInstance',)
    valid_origin_states = ('Stopped',)

    def process(self, resources):
        resources = self.filter_resources(resources, 'NotebookInstanceStatus',
                                          self.valid_origin_states)
        if not len(resources):
            return

        client = local_session(self.manager.session_factory).client('sagemaker')

        for n in resources:
            try:
                client.start_notebook_instance(
                    NotebookInstanceName=n['NotebookInstanceName'])
            except client.exceptions.ResourceNotFound:
                pass


@NotebookInstance.action_registry.register('stop')
class StopNotebookInstance(BaseAction):
    """Stop sagemaker-notebook(s)

    :example:

    .. code-block:: yaml

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

    def process(self, resources):
        resources = self.filter_resources(resources, 'NotebookInstanceStatus',
                                          self.valid_origin_states)
        if not len(resources):
            return

        client = local_session(self.manager.session_factory).client('sagemaker')

        for n in resources:
            try:
                client.stop_notebook_instance(
                    NotebookInstanceName=n['NotebookInstanceName'])
            except client.exceptions.ResourceNotFound:
                pass


@NotebookInstance.action_registry.register('delete')
class DeleteNotebookInstance(BaseAction):
    """Deletes sagemaker-notebook(s)

    :example:

    .. code-block:: yaml

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

    def process(self, resources):
        resources = self.filter_resources(resources, 'NotebookInstanceStatus',
                                          self.valid_origin_states)
        if not len(resources):
            return

        client = local_session(self.manager.session_factory).client('sagemaker')

        for n in resources:
            try:
                client.delete_notebook_instance(
                    NotebookInstanceName=n['NotebookInstanceName'])
            except client.exceptions.ResourceNotFound:
                pass


@NotebookInstance.filter_registry.register('security-group')
class NotebookSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[]"


@NotebookInstance.filter_registry.register('subnet')
class NotebookSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "SubnetId"


@NotebookInstance.filter_registry.register('kms-key')
@SagemakerEndpointConfig.filter_registry.register('kms-key')
class NotebookKmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = "KmsKeyId"


@Model.action_registry.register('delete')
class DeleteModel(BaseAction):
    """Deletes sagemaker-model(s)

    :example:

    .. code-block:: yaml

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

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('sagemaker')

        for m in resources:
            try:
                client.delete_model(ModelName=m['ModelName'])
            except client.exceptions.ResourceNotFound:
                pass


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

    def process(self, jobs):
        client = local_session(self.manager.session_factory).client('sagemaker')

        for j in jobs:
            try:
                client.stop_training_job(TrainingJobName=j['TrainingJobName'])
            except client.exceptions.ResourceNotFound:
                pass


@SagemakerEndpoint.action_registry.register('delete')
class SagemakerEndpointDelete(BaseAction):
    """Delete a SageMaker endpoint

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-sagemaker-endpoint
            resource: sagemaker-endpoint
            filters:
              - EndpointName: sagemaker-ep--2018-01-01-00-00-00
            actions:
              - type: delete
    """
    permissions = (
        'sagemaker:DeleteEndpoint',
        'sagemaker:DeleteEndpointConfig')
    schema = type_schema('delete')

    def process(self, endpoints):
        client = local_session(self.manager.session_factory).client('sagemaker')
        for e in endpoints:
            try:
                client.delete_endpoint(EndpointName=e['EndpointName'])
            except client.exceptions.ResourceNotFound:
                pass


@SagemakerEndpointConfig.action_registry.register('delete')
class SagemakerEndpointConfigDelete(BaseAction):
    """Delete a SageMaker endpoint

    :example:

    .. code-block:: yaml

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

    def process(self, endpoints):
        client = local_session(self.manager.session_factory).client('sagemaker')
        for e in endpoints:
            try:
                client.delete_endpoint_config(
                    EndpointConfigName=e['EndpointConfigName'])
            except client.exceptions.ResourceNotFound:
                pass


@SagemakerTransformJob.action_registry.register('stop')
class SagemakerTransformJobStop(BaseAction):
    """Stops a SageMaker Transform job

    :example:

    .. code-block:: yaml

        policies:
          - name: stop-tranform-job
            resource: sagemaker-transform-job
            filters:
              - TransformJobName: ml-job-10
            actions:
              - stop
    """
    schema = type_schema('stop')
    permissions = ('sagemaker:StopTransformJob',)

    def process(self, jobs):
        client = local_session(self.manager.session_factory).client('sagemaker')

        for j in jobs:
            try:
                client.stop_transform_job(TransformJobName=j['TransformJobName'])
            except client.exceptions.ResourceNotFound:
                pass
