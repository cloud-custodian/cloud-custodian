# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from botocore.exceptions import ClientError
from concurrent.futures import as_completed
from c7n.manager import resources, ResourceManager
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, chunks, type_schema
from c7n.actions import BaseAction, ActionRegistry, RemovePolicyBase
from c7n.exceptions import PolicyValidationError
from c7n.filters.vpc import SubnetFilter, SecurityGroupFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.tags import universal_augment
from c7n.filters import ValueFilter, FilterRegistry, CrossAccountAccessFilter
from c7n import query, utils
from c7n.resources.account import GlueCatalogEncryptionEnabled
from c7n.filters.kms import KmsRelatedFilter


@resources.register('glue-connection')
class GlueConnection(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_connections', 'ConnectionList', {'HidePassword': True})
        id = name = 'Name'
        date = 'CreationTime'
        arn_type = "connection"
        cfn_type = 'AWS::Glue::Connection'
        universal_taggable = object()

    augment = universal_augment


@GlueConnection.filter_registry.register('subnet')
class ConnectionSubnetFilter(SubnetFilter):

    RelatedIdsExpression = 'PhysicalConnectionRequirements.SubnetId'


@GlueConnection.filter_registry.register('security-group')
class ConnectionSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = 'PhysicalConnectionRequirements.' \
                           'SecurityGroupIdList[]'


@GlueConnection.action_registry.register('delete')
class DeleteConnection(BaseAction):
    """Delete a connection from the data catalog

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-jdbc-connections
            resource: glue-connection
            filters:
              - ConnectionType: JDBC
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    permissions = ('glue:DeleteConnection',)

    def delete_connection(self, r):
        client = local_session(self.manager.session_factory).client('glue')
        try:
            client.delete_connection(ConnectionName=r['Name'])
        except ClientError as e:
            if e.response['Error']['Code'] != 'EntityNotFoundException':
                raise

    def process(self, resources):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.delete_connection, resources))


@resources.register('glue-dev-endpoint')
class GlueDevEndpoint(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_dev_endpoints', 'DevEndpoints', None)
        id = name = 'EndpointName'
        date = 'CreatedTimestamp'
        arn_type = "devEndpoint"
        universal_taggable = True
        cfn_type = 'AWS::Glue::DevEndpoint'

    augment = universal_augment


@GlueDevEndpoint.filter_registry.register('subnet')
class EndpointSubnetFilter(SubnetFilter):

    RelatedIdsExpression = 'SubnetId'


@GlueDevEndpoint.action_registry.register('delete')
class DeleteDevEndpoint(BaseAction):
    """Deletes public Glue Dev Endpoints

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-public-dev-endpoints
            resource: glue-dev-endpoint
            filters:
              - PublicAddress: present
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    permissions = ('glue:DeleteDevEndpoint',)

    def delete_dev_endpoint(self, client, endpoint_set):
        for e in endpoint_set:
            try:
                client.delete_dev_endpoint(EndpointName=e['EndpointName'])
            except client.exceptions.AlreadyExistsException:
                pass

    def process(self, resources):
        futures = []
        client = local_session(self.manager.session_factory).client('glue')
        with self.executor_factory(max_workers=2) as w:
            for endpoint_set in chunks(resources, size=5):
                futures.append(w.submit(self.delete_dev_endpoint, client, endpoint_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting glue dev endpoint \n %s",
                        f.exception())


@resources.register('glue-job')
class GlueJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_jobs', 'Jobs', None)
        id = name = 'Name'
        date = 'CreatedOn'
        arn_type = 'job'
        universal_taggable = True
        cfn_type = 'AWS::Glue::Job'

    permissions = ('glue:GetJobs',)
    augment = universal_augment


@GlueJob.action_registry.register('delete')
class DeleteJob(BaseAction):

    schema = type_schema('delete')
    permissions = ('glue:DeleteJob',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')
        for r in resources:
            try:
                client.delete_job(JobName=r['Name'])
            except client.exceptions.EntityNotFoundException:
                continue


@GlueJob.action_registry.register('toggle-metrics')
class GlueJobToggleMetrics(BaseAction):
    """Enable or disable CloudWatch metrics for a Glue job

    :example:

    .. code-block:: yaml

        policies:
          - name: gluejob-enable-metrics
            resource: glue-job
            filters:
              - type: value
                key: 'DefaultArguments."--enable-metrics"'
                value: absent
            actions:
              - type: toggle-metrics
                enabled: true
    """
    schema = type_schema(
        'toggle-metrics',
        enabled={'type': 'boolean'},
        required=['enabled'],
    )
    permissions = ('glue:UpdateJob',)

    def prepare_params(self, r):
        client = local_session(self.manager.session_factory).client('glue')
        update_keys = client.meta._service_model.shape_for('JobUpdate').members
        want_keys = set(r).intersection(update_keys) - {'AllocatedCapacity'}
        params = {k: r[k] for k in want_keys}

        # Can't specify MaxCapacity when updating/creating a job if
        # job configuration includes WorkerType or NumberOfWorkers
        if 'WorkerType' in params or 'NumberOfWorkers' in params:
            del params['MaxCapacity']

        # Can't specify Timeout when updating Ray jobs.
        # Removing Timeout preserves default setting.
        if params['Command']['Name'] == 'glueray':
            del params['Timeout']

        if self.data.get('enabled'):
            if 'DefaultArguments' not in params:
                params['DefaultArguments'] = {}
            params["DefaultArguments"]["--enable-metrics"] = ""
        else:
            if 'DefaultArguments' in params and \
                '--enable-metrics' in params['DefaultArguments']:
                del params["DefaultArguments"]["--enable-metrics"]

        return params

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')

        for r in resources:
            try:
                job_name = r["Name"]
                updated_resource = self.prepare_params(r)
                client.update_job(JobName=job_name, JobUpdate=updated_resource)
            except Exception as e:
                self.log.error('Error updating glue job: {}'.format(e))


@resources.register('glue-crawler')
class GlueCrawler(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_crawlers', 'Crawlers', None)
        id = name = 'Name'
        date = 'CreatedOn'
        arn_type = 'crawler'
        state_key = 'State'
        universal_taggable = True
        cfn_type = 'AWS::Glue::Crawler'

    augment = universal_augment


class SecurityConfigFilter(RelatedResourceFilter):
    """Filters glue crawlers with security configurations

    :example:

    .. code-block:: yaml

            policies:
              - name: need-kms-cloudwatch
                resource: glue-crawler
                filters:
                  - type: security-config
                    key: EncryptionConfiguration.CloudWatchEncryption.CloudWatchEncryptionMode
                    op: ne
                    value: SSE-KMS

    To find resources missing any security configuration all set `missing: true` on the filter.
    """

    RelatedResource = "c7n.resources.glue.GlueSecurityConfiguration"
    AnnotationKey = "matched-security-config"
    RelatedIdsExpression = None

    schema = type_schema(
        'security-config',
        missing={'type': 'boolean', 'default': False},
        rinherit=ValueFilter.schema)

    def validate(self):
        if self.data.get('missing'):
            return self
        else:
            return super(SecurityConfigFilter, self).validate()

    def process(self, resources, event=None):
        if self.data.get('missing'):
            return [r for r in resources if self.RelatedIdsExpression not in r]
        return super(SecurityConfigFilter, self).process(resources, event=None)


@GlueDevEndpoint.filter_registry.register('security-config')
class DevEndpointSecurityConfigFilter(SecurityConfigFilter):
    RelatedIdsExpression = 'SecurityConfiguration'


@GlueJob.filter_registry.register('security-config')
class GlueJobSecurityConfigFilter(SecurityConfigFilter):
    RelatedIdsExpression = 'SecurityConfiguration'


@GlueCrawler.filter_registry.register('security-config')
class GlueCrawlerSecurityConfigFilter(SecurityConfigFilter):

    RelatedIdsExpression = 'CrawlerSecurityConfiguration'


@GlueCrawler.action_registry.register('delete')
class DeleteCrawler(BaseAction):

    schema = type_schema('delete')
    permissions = ('glue:DeleteCrawler',)
    valid_origin_states = ('READY', 'FAILED')

    def process(self, resources):
        resources = self.filter_resources(resources, 'State', self.valid_origin_states)

        client = local_session(self.manager.session_factory).client('glue')
        for r in resources:
            try:
                client.delete_crawler(Name=r['Name'])
            except client.exceptions.EntityNotFoundException:
                continue


@resources.register('glue-database')
class GlueDatabase(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_databases', 'DatabaseList', None)
        id = name = 'Name'
        date = 'CreatedOn'
        arn_type = 'database'
        state_key = 'State'
        cfn_type = 'AWS::Glue::Database'


@GlueDatabase.action_registry.register('delete')
class DeleteDatabase(BaseAction):

    schema = type_schema('delete')
    permissions = ('glue:DeleteDatabase',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')
        for r in resources:
            try:
                client.delete_database(Name=r['Name'])
            except client.exceptions.EntityNotFoundException:
                continue


@resources.register('glue-table')
class GlueTable(query.ChildResourceManager):

    child_source = 'describe-table'

    class resource_type(TypeInfo):
        service = 'glue'
        parent_spec = ('glue-database', 'DatabaseName', None)
        enum_spec = ('get_tables', 'TableList', None)
        id = name = 'Name'
        date = 'CreatedOn'
        arn_type = 'table'


@query.sources.register('describe-table')
class DescribeTable(query.ChildDescribeSource):

    def get_query(self):
        return super(DescribeTable, self).get_query(capture_parent_id=True)

    def augment(self, resources):
        result = []
        for parent_id, r in resources:
            r['DatabaseName'] = parent_id
            result.append(r)
        return result


@GlueTable.action_registry.register('delete')
class DeleteTable(BaseAction):

    schema = type_schema('delete')
    permissions = ('glue:DeleteTable',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')
        for r in resources:
            try:
                client.delete_table(DatabaseName=r['DatabaseName'], Name=r['Name'])
            except client.exceptions.EntityNotFoundException:
                continue


@resources.register('glue-classifier')
class GlueClassifier(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_classifiers', 'Classifiers', None)
        id = name = 'Name'
        date = 'CreationTime'
        arn_type = 'classifier'
        config_type = cfn_type = 'AWS::Glue::Classifier'


@GlueClassifier.action_registry.register('delete')
class DeleteClassifier(BaseAction):

    schema = type_schema('delete')
    permissions = ('glue:DeleteClassifier',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')
        for r in resources:
            # Extract the classifier from the resource, see below
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glue.html#Glue.Client.get_classifier
            classifier = list(r.values())[0]
            try:
                client.delete_classifier(Name=classifier['Name'])
            except client.exceptions.EntityNotFoundException:
                continue


@resources.register('glue-ml-transform')
class GlueMLTransform(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_ml_transforms', 'Transforms', None)
        name = 'Name'
        id = 'TransformId'
        arn_type = 'mlTransform'
        universal_taggable = object()
        config_type = cfn_type = 'AWS::Glue::MLTransform'

    source_mapping = {'describe': query.DescribeWithResourceTags,
                      'config': query.ConfigSource}

    def get_permissions(self):
        return ('glue:GetMLTransforms',)


@GlueMLTransform.action_registry.register('delete')
class DeleteMLTransform(BaseAction):

    schema = type_schema('delete')
    permissions = ('glue:DeleteMLTransform',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')
        for r in resources:
            try:
                client.delete_ml_transform(TransformId=r['TransformId'])
            except client.exceptions.EntityNotFoundException:
                continue


@resources.register('glue-security-configuration')
class GlueSecurityConfiguration(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_security_configurations', 'SecurityConfigurations', None)
        id = name = 'Name'
        arn_type = 'securityConfiguration'
        date = 'CreatedTimeStamp'
        cfn_type = 'AWS::Glue::SecurityConfiguration'


@GlueSecurityConfiguration.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    schema = type_schema(
        'kms-key',
        rinherit=ValueFilter.schema,
        **{'key-type': {'type': 'string', 'enum': [
            's3', 'cloudwatch', 'job-bookmarks', 'all']},
            'match-resource': {'type': 'boolean'},
            'operator': {'enum': ['and', 'or']}})

    RelatedIdsExpression = ''

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        key_type_to_related_ids = {
            's3': 'EncryptionConfiguration.S3Encryption[].KmsKeyArn',
            'cloudwatch': 'EncryptionConfiguration.CloudWatchEncryption.KmsKeyArn',
            'job-bookmarks': 'EncryptionConfiguration.JobBookmarksEncryption.KmsKeyArn',
            'all': 'EncryptionConfiguration.*[][].KmsKeyArn'
        }
        key_type = self.data.get('key_type', 'all')
        self.RelatedIdsExpression = key_type_to_related_ids[key_type]


@GlueSecurityConfiguration.action_registry.register('delete')
class DeleteSecurityConfiguration(BaseAction):

    schema = type_schema('delete')
    permissions = ('glue:DeleteSecurityConfiguration',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')
        for r in resources:
            try:
                client.delete_security_configuration(Name=r['Name'])
            except client.exceptions.EntityNotFoundException:
                continue


@resources.register('glue-trigger')
class GlueTrigger(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_triggers', 'Triggers', None)
        id = name = 'Name'
        arn_type = 'trigger'
        universal_taggable = object()
        cfn_type = 'AWS::Glue::Trigger'

    augment = universal_augment


@GlueTrigger.action_registry.register('delete')
class DeleteTrigger(BaseAction):

    schema = type_schema('delete')
    permissions = ('glue:DeleteTrigger',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')
        for r in resources:
            try:
                client.delete_trigger(Name=r['Name'])
            except client.exceptions.EntityNotFoundException:
                continue


@resources.register('glue-workflow')
class GlueWorkflow(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('list_workflows', 'Workflows', None)
        detail_spec = ('get_workflow', 'Name', None, 'Workflow')
        id = name = 'Name'
        arn_type = 'workflow'
        universal_taggable = object()
        cfn_type = 'AWS::Glue::Workflow'

    def augment(self, resources):
        return universal_augment(
            self, super(GlueWorkflow, self).augment(resources))


@GlueWorkflow.action_registry.register('delete')
class DeleteWorkflow(BaseAction):

    schema = type_schema('delete')
    permissions = ('glue:DeleteWorkflow',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')
        for r in resources:
            try:
                client.delete_workflow(Name=r['Name'])
            except client.exceptions.EntityNotFoundException:
                continue


@GlueWorkflow.filter_registry.register('security-config')
class GlueWorkflowSecurityConfigFilter(SecurityConfigFilter):
    RelatedIdsExpression = 'SecurityConfiguration'


@resources.register('glue-catalog')
class GlueDataCatalog(ResourceManager):

    filter_registry = FilterRegistry('glue-catalog.filters')
    action_registry = ActionRegistry('glue-catalog.actions')
    retry = staticmethod(QueryResourceManager.retry)

    class resource_type(query.TypeInfo):
        service = 'glue'
        arn_type = 'catalog'
        id = name = 'CatalogId'
        cfn_type = 'AWS::Glue::DataCatalogEncryptionSettings'

    @classmethod
    def get_permissions(cls):
        return ('glue:GetDataCatalogEncryptionSettings',)

    @classmethod
    def has_arn(cls):
        return True

    def get_model(self):
        return self.resource_type

    def _get_catalog_encryption_settings(self):
        client = utils.local_session(self.session_factory).client('glue')
        settings = client.get_data_catalog_encryption_settings()
        settings['CatalogId'] = self.config.account_id
        settings.pop('ResponseMetadata', None)
        return [settings]

    def resources(self):
        return self.filter_resources(self._get_catalog_encryption_settings())

    def get_resources(self, resource_ids):
        return [{'CatalogId': self.config.account_id}]


@GlueDataCatalog.filter_registry.register('kms-key')
class GlueCatalogKmsFilter(KmsRelatedFilter):

    schema = type_schema(
        'kms-key',
        rinherit=ValueFilter.schema,
        **{'key-type': {'type': 'string', 'enum': [
            'EncryptionAtRest', 'ConnectionPasswordEncryption']},
            'required': ['key-type'],
            'match-resource': {'type': 'boolean'},
            'operator': {'enum': ['and', 'or']}})

    permissions = ('glue:GetDataCatalogEncryptionSettings',)

    RelatedIdsExpression = ''

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        key_type_to_related_ids = {
            'EncryptionAtRest': 'DataCatalogEncryptionSettings.EncryptionAtRest.SseAwsKmsKeyId',
            'ConnectionPasswordEncryption':
              'DataCatalogEncryptionSettings.ConnectionPasswordEncryption.AwsKmsKeyId'
        }
        self.RelatedIdsExpression = key_type_to_related_ids.get(self.data.get('key-type'))


@GlueDataCatalog.action_registry.register('set-encryption')
class GlueDataCatalogEncryption(BaseAction):
    """Modifies glue data catalog encryption based on specified parameter
    As per docs, we can enable catalog encryption or only password encryption,
    not both

    :example:

    .. code-block:: yaml

            policies:
              - name: data-catalog-encryption
                resource: glue-catalog
                filters:
                  - type: value
                    key: DataCatalogEncryptionSettings.EncryptionAtRest.CatalogEncryptionMode
                    value: DISABLED
                    op: eq
                actions:
                  - type: set-encryption
                    attributes:
                      EncryptionAtRest:
                        CatalogEncryptionMode: SSE-KMS
                        SseAwsKmsKeyId: alias/aws/glue
    """

    schema = type_schema(
        'set-encryption',
        required=['attributes'],
        attributes={
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'EncryptionAtRest': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['CatalogEncryptionMode'],
                    'properties': {
                        'CatalogEncryptionMode': {'enum': ['DISABLED', 'SSE-KMS']},
                        'SseAwsKmsKeyId': {'type': 'string'}
                    }
                },
                'ConnectionPasswordEncryption': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['ReturnConnectionPasswordEncrypted'],
                    'properties': {
                        'ReturnConnectionPasswordEncrypted': {'type': 'boolean'},
                        'AwsKmsKeyId': {'type': 'string'}
                    }
                }
            }
        }
    )

    permissions = ('glue:PutDataCatalogEncryptionSettings',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glue')
        self.process_catalog_encryption(client, resources)

    def process_catalog_encryption(self, client, resources):
        # there is one glue data catalog per account
        if 'DataCatalogEncryptionSettings' not in resources[0]:
            resources = self.manager.resources()
        enc_config = resources[0]['DataCatalogEncryptionSettings']
        updated_config = {**enc_config, **self.data['attributes']}
        if enc_config == updated_config:
            return
        client.put_data_catalog_encryption_settings(
            DataCatalogEncryptionSettings=updated_config)


@GlueDataCatalog.filter_registry.register('glue-security-config')
class GlueCatalogEncryptionFilter(GlueCatalogEncryptionEnabled):
    """Filter glue catalog by its glue encryption status and KMS key

    :example:

    .. code-block:: yaml

      policies:
        - name: glue-catalog-security-config
          resource: aws.glue-catalog
          filters:
            - type: glue-security-config
              SseAwsKmsKeyId: alias/aws/glue

    """


@GlueDataCatalog.filter_registry.register('cross-account')
class GlueCatalogCrossAccount(CrossAccountAccessFilter):
    """Filter glue catalog if it has cross account permissions

    :example:

    .. code-block:: yaml

      policies:
        - name: catalog-cross-account
          resource: aws.glue-catalog
          filters:
            - type: cross-account

    """
    permissions = ('glue:GetResourcePolicy',)
    policy_annotation = "c7n:AccessPolicy"

    def get_resource_policy(self, r):
        client = local_session(self.manager.session_factory).client('glue')
        if self.policy_annotation in r:
            return r[self.policy_annotation]
        try:
            policy = client.get_resource_policy().get('PolicyInJson')
        except client.exceptions.EntityNotFoundException:
            policy = {}
        r[self.policy_annotation] = policy
        return policy


@GlueDataCatalog.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from Glue Data Catalog

    :example:

    .. code-block:: yaml

           policies:
              - name: remove-glue-catalog-cross-account
                resource: aws.glue-catalog
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """
    permissions = ('glue:PutResourcePolicy',)
    policy_annotation = "c7n:AccessPolicy"

    def validate(self):
        for f in self.manager.iter_filters():
            if isinstance(f, GlueCatalogCrossAccount):
                return self
        raise PolicyValidationError(
            '`remove-statements` may only be used in '
            'conjunction with `cross-account` filter on %s' % (self.manager.data,))

    def process(self, resources):
        resource = resources[0]
        client = local_session(self.manager.session_factory).client('glue')
        if resource.get(self.policy_annotation):
            p = json.loads(resource[self.policy_annotation])
            statements, found = self.process_policy(
                p, resource, CrossAccountAccessFilter.annotation_key)
            if not found:
                return
            if statements:
                client.put_resource_policy(PolicyInJson=json.dumps(p))
            else:
                client.delete_resource_policy()
