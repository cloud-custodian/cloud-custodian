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
from c7n.tags import universal_augment, register_universal_tags
from c7n.filters import StateTransitionFilter


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

    permissions = ('glue:GetDevEndpoints',)
    augment = universal_augment


register_universal_tags(GlueDevEndpoint.filter_registry, GlueDevEndpoint.action_registry)


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

    permissions = ('glue:GetJobs',)
    augment = universal_augment


register_universal_tags(GlueJob.filter_registry, GlueJob.action_registry)


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

    permissions = ('glue:GetCrawlers',)
    augment = universal_augment


register_universal_tags(GlueCrawler.filter_registry, GlueCrawler.action_registry)


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
