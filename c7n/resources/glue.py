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
from concurrent.futures import as_completed

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, chunks, type_schema
from c7n.actions import BaseAction
from c7n.filters.vpc import SubnetFilter, SecurityGroupFilter
from c7n.tags import universal_augment
from c7n.filters import StateTransitionFilter, ValueFilter
from c7n import query


@resources.register('glue-connection')
class GlueConnection(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'glue'
        enum_spec = ('get_connections', 'ConnectionList', None)
        id = name = 'Name'
        date = 'CreationTime'
        arn_type = "connection"

    permissions = ('glue:GetConnections',)


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

    permissions = ('glue:GetDevEndpoints',)
    augment = universal_augment


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

    permissions = ('glue:GetCrawlers',)
    augment = universal_augment


class SecurityConfigFilter(ValueFilter):
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

    permissions = ('glue:GetSecurityConfiguration',)
    annotation_key = 'c7n:SecurityConfiguration'
    security_name_key = None  # set in subclass for particular resource
    schema = type_schema(
        'security-config',
        missing={'type': 'boolean', 'default': False},
        rinherit=ValueFilter.schema)

    def validate(self):
        if self.data.get('missing'):
            return
        super().validate()

    def process(self, resources, event=None):
        resources = self.initialize(resources)
        if self.data.get('missing'):
            return resources
        return super(ValueFilter, self).process(resources, event)

    def __call__(self, r):
        if self.annotation_key not in r:
            return False
        return self.match(r[self.annotation_key])

    def initialize(self, resources):
        if self.data.get('missing'):
            return [r for r in resources if self.security_name_key not in r]

        # fetch security configurations by name for the resources
        client = local_session(self.manager.session_factory).client('glue')
        # Get the security configurations that aren't already cached.
        security_config_names = {
            r.get(self.security_name_key) for r in resources
            if self.annotation_key not in r}
        if None in security_config_names:
            security_config_names.remove(None)

        security_config_map = {}
        for n in security_config_names:
            try:
                security_config_map[n] = client.get_security_configuration(
                    Name=n)['SecurityConfiguration']
            except client.exceptions.EntityNotFoundException:
                continue

        for r in resources:
            if self.security_name_key not in r or self.annotation_key in r:
                continue
            r[self.annotation_key] = security_config_map[r[self.security_name_key]]
        return resources


@GlueDevEndpoint.filter_registry.register('security-config')
class DevEndpointSecurityConfigFilter(SecurityConfigFilter):
    security_name_key = 'SecurityConfiguration'


@GlueJob.filter_registry.register('security-config')
class GlueJobSecurityConfigFilter(SecurityConfigFilter):
    security_name_key = 'SecurityConfiguration'


@GlueCrawler.filter_registry.register('security-config')
class GlueCrawlerSecurityConfigFilter(SecurityConfigFilter):
    security_name_key = 'CrawlerSecurityConfiguration'


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
        name = 'Name'
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
