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
from botocore.exceptions import ClientError
from concurrent.futures import as_completed
from .aws import shape_validate
from c7n.manager import resources, ResourceManager
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, chunks, type_schema
from c7n.actions import BaseAction, ActionRegistry
from c7n.filters.vpc import SubnetFilter, SecurityGroupFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.tags import universal_augment
from c7n.filters import StateTransitionFilter, ValueFilter, FilterRegistry, CrossAccountAccessFilter
from c7n import query, utils
from c7n.resources.account import GlueCatalogEncryptionEnabled


@resources.register('glue-connection')
class GlueConnection(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_connections', 'ConnectionList', None)
        id = name = 'Name'
        date = 'CreationTime'
        arn_type = "connection"


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
class DeleteCrawler(BaseAction, StateTransitionFilter):

    schema = type_schema('delete')
    permissions = ('glue:DeleteCrawler',)
    valid_origin_states = ('READY', 'FAILED')

    def process(self, resources):
        resources = self.filter_resource_state(resources)

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
        query = super(DescribeTable, self).get_query()
        query.capture_parent_id = True
        return query

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

    augment = universal_augment

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
        settings.pop('ResponseMetadata', None)
        return [settings]

    def resources(self):
        return self.filter_resources(self._get_catalog_encryption_settings())


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
        attributes={'type': 'object', "minItems": 1},
        required=('attributes',))

    permissions = ('glue:PutDataCatalogEncryptionSettings',)
    shape = 'PutDataCatalogEncryptionSettingsRequest'

    def validate(self):
        attrs = {}
        attrs['DataCatalogEncryptionSettings'] = self.data['attributes']
        return shape_validate(attrs, self.shape, 'glue')

    def process(self, catalog):
        client = local_session(self.manager.session_factory).client('glue')
        # there is one glue data catalog per account
        client.put_data_catalog_encryption_settings(
            DataCatalogEncryptionSettings=self.data['attributes'])


@GlueDataCatalog.filter_registry.register('glue-security-config')
class GlueCatalogEncryptionFilter(GlueCatalogEncryptionEnabled):
    """Filter aws account by its glue encryption status and KMS key

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
