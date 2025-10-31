# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.utils import local_session, type_schema, QueryParser
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction, universal_augment
from c7n.filters.vpc import SubnetFilter, SecurityGroupFilter, NetworkLocation
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters.offhours import OffHour, OnHour


class NotebookDescribe(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('sagemaker')

        def _augment(r):
            # List tags for the Notebook-Instance & set as attribute
            tags = self.manager.retry(client.list_tags,
                ResourceArn=r['NotebookInstanceArn'])['Tags']
            r['Tags'] = tags
            return r

        # Describe notebook-instance & then list tags
        resources = super().augment(resources)
        return list(map(_augment, resources))


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
        config_type = cfn_type = 'AWS::SageMaker::NotebookInstance'
        permissions_augment = ("sagemaker:ListTags",)

    source_mapping = {'describe': NotebookDescribe, 'config': ConfigSource}


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
        self.queries = SagemakerJobQueryParser.parse(
            self.data.get('query', [
                {'StatusEquals': 'InProgress'}]))

    def resources(self, query=None):
        query = query or {}
        for q in self.queries:
            query.update(q)
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
        self.queries = SagemakerJobQueryParser.parse(
            self.data.get('query', [
                {'StatusEquals': 'InProgress'}]))

    def resources(self, query=None):
        query = query or {}
        for q in self.queries:
            query.update(q)
        return super(SagemakerTransformJob, self).resources(query=query)

    def augment(self, jobs):
        client = local_session(self.session_factory).client('sagemaker')

        def _augment(j):
            tags = self.retry(client.list_tags,
                ResourceArn=j['TransformJobArn'])['Tags']
            j['Tags'] = tags
            return j

        return list(map(_augment, super(SagemakerTransformJob, self).augment(jobs)))


class SagemakerHyperParameterTuningJobDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-hyperparameter-tuning-job')
class SagemakerHyperParameterTuningJob(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_hyper_parameter_tuning_jobs', 'HyperParameterTuningJobSummaries', None)
        detail_spec = (
            'describe_hyper_parameter_tuning_job', 'HyperParameterTuningJobName',
            'HyperParameterTuningJobName', None)
        arn = id = 'HyperParameterTuningJobArn'
        name = 'HyperParameterTuningJobName'
        date = 'CreationTime'
        permission_prefix = 'sagemaker'
        universal_taggable = object()

    source_mapping = {'describe': SagemakerHyperParameterTuningJobDescribe}

    def __init__(self, ctx, data):
        super(SagemakerHyperParameterTuningJob, self).__init__(ctx, data)
        self.queries = SagemakerJobQueryParser.parse(
            self.data.get('query', [
                {'StatusEquals': 'InProgress'}]))

    def resources(self, query=None):
        query = query or {}
        for q in self.queries:
            query.update(q)
        return super(SagemakerHyperParameterTuningJob, self).resources(query=query)


class SagemakerAutoMLDescribeV2(DescribeSource):

    def get_permissions(self):
        perms = super().get_permissions()
        perms.remove('sagemaker:DescribeAutoMlJobV2')
        return perms

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-auto-ml-job')
class SagemakerAutoMLJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_auto_ml_jobs', 'AutoMLJobSummaries', None)
        detail_spec = (
            'describe_auto_ml_job_v2', 'AutoMLJobName', 'AutoMLJobName', None)
        arn = id = 'AutoMLJobArn'
        name = 'AutoMLJobName'
        date = 'CreationTime'
        # override defaults to casing issues
        permissions_augment = ('sagemaker:DescribeAutoMLJobV2',)
        permissions_enum = ('sagemaker:ListAutoMLJobs',)
        universal_taggable = object()

    source_mapping = {'describe': SagemakerAutoMLDescribeV2}

    def __init__(self, ctx, data):
        super(SagemakerAutoMLJob, self).__init__(ctx, data)
        self.queries = SagemakerJobQueryParser.parse(
            self.data.get('query', [
                {'StatusEquals': 'InProgress'}]))

    def resources(self, query=None):
        query = query or {}
        for q in self.queries:
            query.update(q)
        return super(SagemakerAutoMLJob, self).resources(query=query)


class SagemakerCompilationJobDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-compilation-job')
class SagemakerCompilationJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_compilation_jobs', 'CompilationJobSummaries', None)
        detail_spec = (
            'describe_compilation_job', 'CompilationJobName', 'CompilationJobName', None)
        arn = id = 'CompilationJobArn'
        name = 'CompilationJobName'
        date = 'CreationTime'
        permission_prefix = 'sagemaker'
        universal_taggable = object()

    source_mapping = {'describe': SagemakerCompilationJobDescribe}

    def __init__(self, ctx, data):
        super(SagemakerCompilationJob, self).__init__(ctx, data)
        self.queries = CompilationJobQueryParser.parse(
            self.data.get('query', [
                {'StatusEquals': 'INPROGRESS'}]))

    def resources(self, query=None):
        query = query or {}
        for q in self.queries:
            query.update(q)
        return super(SagemakerCompilationJob, self).resources(query=query)


class SagemakerProcessingJobDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-processing-job')
class SagemakerProcessingJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_processing_jobs', 'ProcessingJobSummaries', None)
        detail_spec = (
            'describe_processing_job', 'ProcessingJobName', 'ProcessingJobName', None)
        arn = id = 'ProcessingJobArn'
        name = 'ProcessingJobName'
        date = 'CreationTime'
        permission_prefix = 'sagemaker'
        universal_taggable = object()

    source_mapping = {'describe': SagemakerProcessingJobDescribe}

    def __init__(self, ctx, data):
        super(SagemakerProcessingJob, self).__init__(ctx, data)
        self.queries = SagemakerJobQueryParser.parse(
            self.data.get('query', [
                {'StatusEquals': 'InProgress'}]))

    def resources(self, query=None):
        query = query or {}
        for q in self.queries:
            query.update(q)
        return super(SagemakerProcessingJob, self).resources(query=query)


class SagemakerModelBiasJobDefinitionDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-model-bias-job-definition')
class SagemakerModelBiasJobDefinition(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_model_bias_job_definitions', 'JobDefinitionSummaries', None)
        detail_spec = (
            'describe_model_bias_job_definition', 'JobDefinitionName',
            'MonitoringJobDefinitionName', None)
        arn = id = 'JobDefinitionArn'
        name = 'JobDefinitionName'
        date = 'CreationTime'
        permissions_prefix = 'sagemaker'
        universal_taggable = object()

    source_mapping = {'describe': SagemakerModelBiasJobDefinitionDescribe}


class SagemakerJobQueryParser(QueryParser):

    QuerySchema = {
        'NameContains': str,
        'StatusEquals': ('InProgress', 'Completed', 'Failed', 'Stopping', 'Stopped'),
        'CreationTimeAfter': 'date',
        'CreationTimeBefore': 'date',
        'LastModifiedTimeAfter': 'date',
        'LastModifiedTimeBefore': 'date',
        'MaxResults': int,
    }
    multi_value = False
    type_name = 'Sagemaker Job'


class CompilationJobQueryParser(SagemakerJobQueryParser):

    QuerySchema = {
        'NameContains': str,
        'StatusEquals': ('INPROGRESS', 'COMPLETED', 'FAILED', 'STARTING', 'STOPPING', 'STOPPED'),
        'CreationTimeAfter': 'date',
        'CreationTimeBefore': 'date',
        'LastModifiedTimeAfter': 'date',
        'LastModifiedTimeBefore': 'date',
        'MaxResults': int,
    }


class EndpointDescribe(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('sagemaker')

        def _augment(e):
            tags = self.manager.retry(client.list_tags,
                ResourceArn=e['EndpointArn'])['Tags']
            e['Tags'] = tags
            return e

        # Describe endpoints & then list tags
        endpoints = super().augment(resources)
        return list(map(_augment, endpoints))


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

    source_mapping = {'describe': EndpointDescribe}


SagemakerEndpoint.filter_registry.register('marked-for-op', TagActionFilter)


class EndpointConfigDescribe(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('sagemaker')

        def _augment(e):
            tags = self.manager.retry(client.list_tags,
                ResourceArn=e['EndpointConfigArn'])['Tags']
            e['Tags'] = tags
            return e

        endpoints = super().augment(resources)
        return list(map(_augment, endpoints))


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
        config_type = cfn_type = 'AWS::SageMaker::EndpointConfig'
        permissions_augment = ('sagemaker:ListTags',)

    source_mapping = {'describe': EndpointConfigDescribe, 'config': ConfigSource}


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


class SagemakerClusterDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-cluster')
class Cluster(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_clusters', 'ClusterSummaries', None)
        detail_spec = (
            'describe_cluster', 'ClusterName',
            'ClusterName', None)
        arn = id = 'ClusterArn'
        name = 'ClusterName'
        date = 'CreationTime'
        cfn_type = None
        permission_prefix = 'sagemaker'
        universal_taggable = object()

    source_mapping = {'describe': SagemakerClusterDescribe}


class SagemakerDataQualityJobDefinitionDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-data-quality-job-definition')
class SagemakerDataQualityJobDefinition(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_data_quality_job_definitions', 'JobDefinitionSummaries', None)
        detail_spec = ('describe_data_quality_job_definition', 'JobDefinitionName',
                       'MonitoringJobDefinitionName', None)
        arn = id = 'JobDefinitionArn'
        name = 'JobDefinitionName'
        date = 'CreationTime'
        cfn_type = 'AWS::SageMaker::DataQualityJobDefinition'
        permission_prefix = 'sagemaker'
        filter_name = 'EndpointName'
        filter_type = 'scalar'
        universal_taggable = object()

    source_mapping = {'describe': SagemakerDataQualityJobDefinitionDescribe}


class SagemakerModelExplainabilityJobDefinitionDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-model-explainability-job-definition')
class SagemakerModelExplainabilityJobDefinition(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_model_explainability_job_definitions', 'JobDefinitionSummaries', None)
        detail_spec = ('describe_model_explainability_job_definition', 'JobDefinitionName',
                       'MonitoringJobDefinitionName', None)
        arn = id = 'JobDefinitionArn'
        name = 'JobDefinitionName'
        date = 'CreationTime'
        cfn_type = 'AWS::SageMaker::ModelExplainabilityJobDefinition'
        permission_prefix = 'sagemaker'
        filter_name = 'EndpointName'
        filter_type = 'scalar'
        universal_taggable = object()

    source_mapping = {'describe': SagemakerModelExplainabilityJobDefinitionDescribe}


class SagemakerModelQualityJobDefinitionDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-model-quality-job-definition')
class SagemakerModelQualityJobDefinition(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_model_quality_job_definitions', 'JobDefinitionSummaries', None)
        detail_spec = ('describe_model_quality_job_definition', 'JobDefinitionName',
                       'MonitoringJobDefinitionName', None)
        arn = id = 'JobDefinitionArn'
        name = 'JobDefinitionName'
        date = 'CreationTime'
        cfn_type = 'AWS::SageMaker::ModelQualityJobDefinition'
        permission_prefix = 'sagemaker'
        filter_name = 'EndpointName'
        filter_type = 'scalar'
        universal_taggable = object()

    source_mapping = {'describe': SagemakerModelQualityJobDefinitionDescribe}


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


@Cluster.filter_registry.register('security-group')
class ClusterSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "VpcConfig.SecurityGroupIds[]"


@Cluster.filter_registry.register('subnet')
class ClusterSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "VpcConfig.Subnets[]"


@Cluster.filter_registry.register('network-location', NetworkLocation)
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


@SagemakerModelBiasJobDefinition.action_registry.register('delete')
class SagemakerModelBiasJobDefinitionDelete(BaseAction):
    """ Deletes sagemaker-model-bias-job-definition """
    schema = type_schema('delete')
    permissions = ('sagemaker:DeleteModelBiasJobDefinition',)

    def process(self, definitions):
        client = local_session(self.manager.session_factory).client('sagemaker')

        for d in definitions:
            try:
                client.delete_model_bias_job_definition(
                    JobDefinitionName=d['JobDefinitionName'])
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


@SagemakerDataQualityJobDefinition.action_registry.register('delete')
class SagemakerDataQualityJobDefinitionDelete(BaseAction):
    """Delete a SageMaker Data Quality Job Definition

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-sagemaker-data-quality-job-definition
            resource: sagemaker-data-quality-job-definition
            filters:
              - JobDefinitionName: job-def-1
            actions:
              - delete
    """
    schema = type_schema('delete')
    permissions = ('sagemaker:DeleteDataQualityJobDefinition',)

    def process(self, job_definitions):
        client = local_session(self.manager.session_factory).client('sagemaker')
        for j in job_definitions:
            try:
                client.delete_data_quality_job_definition(
                    JobDefinitionName=j['JobDefinitionName'])
            except client.exceptions.ResourceNotFound:
                pass


@SagemakerModelExplainabilityJobDefinition.action_registry.register('delete')
class SagemakerModelExplainabilityJobDefinitionDelete(BaseAction):
    """Delete a SageMaker Model Explainability Job Definition

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-sagemaker-model-explainability-job-definition
            resource: sagemaker-model-explainability-job-definition
            filters:
              - JobDefinitionName: job-def-1
            actions:
              - delete
    """
    schema = type_schema('delete')
    permissions = ('sagemaker:DeleteModelExplainabilityJobDefinition',)

    def process(self, job_definitions):
        client = local_session(self.manager.session_factory).client('sagemaker')
        for j in job_definitions:
            try:
                client.delete_model_explainability_job_definition(
                    JobDefinitionName=j['JobDefinitionName'])
            except client.exceptions.ResourceNotFound:
                pass


@SagemakerModelQualityJobDefinition.action_registry.register('delete')
class SagemakerModelQualityJobDefinitionDelete(BaseAction):
    """Delete a SageMaker Model Quality Job Definition

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-sagemaker-model-quality-job-definition
            resource: sagemaker-model-quality-job-definition
            filters:
              - JobDefinitionName: job-def-1
            actions:
              - delete
    """
    schema = type_schema('delete')
    permissions = ('sagemaker:DeleteModelQualityJobDefinition',)

    def process(self, job_definitions):
        client = local_session(self.manager.session_factory).client('sagemaker')
        for j in job_definitions:
            try:
                client.delete_model_quality_job_definition(
                    JobDefinitionName=j['JobDefinitionName'])
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


@SagemakerHyperParameterTuningJob.action_registry.register('stop')
class SagemakerHyperParameterTuningJobStop(BaseAction):
    """Stops a SageMaker Hyperparameter Tuning job

    :example:

    .. code-block:: yaml

        policies:
          - name: stop-hyperparameter-tuning-job
            resource: sagemaker-hyperparameter-tuning-job
            filters:
              - HyperParameterTuningJobName: ml-job-10
            actions:
              - stop
    """
    schema = type_schema('stop')
    permissions = ('sagemaker:StopHyperParameterTuningJob',)

    def process(self, jobs):
        client = local_session(self.manager.session_factory).client('sagemaker')

        for j in jobs:
            try:
                client.stop_hyper_parameter_tuning_job(HyperParameterTuningJobName=j['HyperParameterTuningJobName'])
            except client.exceptions.ResourceNotFound:
                pass


@SagemakerAutoMLJob.action_registry.register('stop')
class SagemakerAutoMLJobStop(BaseAction):
    """Stops a SageMaker AutoML job

    :example:

    .. code-block:: yaml

        policies:
          - name: stop-automl-job
            resource: sagemaker-auto-ml-job
            filters:
              - AutoMLJobName: ml-job-01
            actions:
              - stop
    """
    schema = type_schema('stop')
    permissions = ('sagemaker:StopAutoMLJob',)

    def process(self, jobs):
        client = local_session(self.manager.session_factory).client('sagemaker')

        for j in jobs:
            try:
                client.stop_auto_ml_job(AutoMLJobName=j['AutoMLJobName'])
            except client.exceptions.ResourceNotFound:
                pass


@SagemakerCompilationJob.action_registry.register('stop')
class SagemakerCompilationJobStop(BaseAction):
    """Stops a SageMaker Compilation job

    :example:

    .. code-block:: yaml

        policies:
          - name: stop-compilation-job
            resource: sagemaker-compilation-job
            filters:
              - CompilationJobName: ml-job-10
            actions:
              - stop
    """
    schema = type_schema('stop')
    permissions = ('sagemaker:StopCompilationJob',)

    def process(self, jobs):
        client = local_session(self.manager.session_factory).client('sagemaker')

        for j in jobs:
            try:
                client.stop_compilation_job(CompilationJobName=j['CompilationJobName'])
            except client.exceptions.ResourceNotFound:
                pass


@SagemakerProcessingJob.action_registry.register('stop')
class SagemakerProcessingJobStop(BaseAction):
    """Stops a Sagemaker Processing job

    :example:

    .. code-block:: yaml

        policies:
          - name: stop-processing-job
            resource: sagemaker-processing-job
            filters:
              - ProcessingJobName: ml-job-10
            actions:
              - stop
    """
    schema = type_schema('stop')
    permissions = ('sagemaker:StopProcessingJob',)

    def process(self, jobs):
        client = local_session(self.manager.session_factory).client('sagemaker')

        for j in jobs:
            try:
                client.stop_processing_job(ProcessingJobName=j['ProcessingJobName'])
            except client.exceptions.ResourceNotFound:
                pass


@Cluster.action_registry.register('delete')
class ClusterDelete(BaseAction):
    """Deletes sagemaker-cluster(s)

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-sagemaker-cluster
            resource: sagemaker-cluster
            filters:
              - "tag:DeleteMe": present
            actions:
              - delete
    """
    schema = type_schema('delete')
    permissions = ('sagemaker:DeleteCluster',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('sagemaker')

        for c in resources:
            try:
                client.delete_cluster(ClusterName=c['ClusterName'])
            except client.exceptions.ResourceNotFound:
                pass


class SagemakerDomainDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('sagemaker-domain')
class SagemakerDomain(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sagemaker'
        enum_spec = ('list_domains', 'Domains', None)
        detail_spec = ('describe_domain', 'DomainId', 'DomainId', None)
        id = 'DomainId'
        arn = 'DomainArn'
        name = 'DomainName'
        cfn_type = 'AWS::SageMaker::Domain'
        permission_prefix = 'sagemaker'
        universal_taggable = object()

    source_mapping = {'describe': SagemakerDomainDescribe}


@SagemakerDomain.filter_registry.register('kms-key')
class SagemakerDomainKmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'KmsKeyId'
