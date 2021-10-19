# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, ChildResourceManager, TypeInfo, ChildDescribeSource
from c7n.utils import local_session, type_schema


@resources.register('transfer-server')
class TransferServer(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'transfer'
        enum_spec = ('list_servers', 'Servers', {'MaxResults': 60})
        detail_spec = (
            'describe_server', 'ServerId', 'ServerId', None)
        id = name = 'ServerId'
        arn_type = "server"
        cfn_type = 'AWS::Transfer::Server'


@TransferServer.action_registry.register('stop')
class StopServer(BaseAction):
    """Action to stop a Transfer Server

    :example:

    .. code-block:: yaml

            policies:
              - name: transfer-server-stop
                resource: transfer-server
                actions:
                  - stop
    """
    valid_status = ('ONLINE', 'STARTING', 'STOP_FAILED',)
    schema = type_schema('stop')
    permissions = ("transfer:StopServer",)

    def process(self, resources):
        resources = self.filter_resources(
            resources, 'State', self.valid_status)
        if not len(resources):
            return

        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_server, resources))

    def process_server(self, server):
        client = local_session(
            self.manager.session_factory).client('transfer')
        try:
            client.stop_server(ServerId=server['ServerId'])
        except ClientError as e:
            self.log.exception(
                "Exception stopping server:\n %s" % e)


@TransferServer.action_registry.register('start')
class StartServer(BaseAction):
    """Action to start a Transfer Server

    :example:

    .. code-block:: yaml

            policies:
              - name: transfer-server-start
                resource: transfer-server
                actions:
                  - start
    """
    valid_status = ('OFFLINE', 'STOPPING', 'START_FAILED', 'STOP_FAILED',)
    schema = type_schema('start')
    permissions = ("transfer:StartServer",)

    def process(self, resources):
        resources = self.filter_resources(
            resources, 'State', self.valid_status)
        if not len(resources):
            return

        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_server, resources))

    def process_server(self, server):
        client = local_session(
            self.manager.session_factory).client('transfer')
        try:
            client.start_server(ServerId=server['ServerId'])
        except ClientError as e:
            self.log.exception(
                "Exception starting server:\n %s" % e)


@TransferServer.action_registry.register('delete')
class DeleteServer(BaseAction):
    """Action to delete a Transfer Server

    :example:

    .. code-block:: yaml

            policies:
              - name: transfer-server-delete
                resource: transfer-server
                actions:
                  - delete
    """
    schema = type_schema('delete')
    permissions = ("transfer:DeleteServer",)

    def process(self, resources):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_server, resources))

    def process_server(self, server):
        client = local_session(
            self.manager.session_factory).client('transfer')
        try:
            client.delete_server(ServerId=server['ServerId'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting server:\n %s" % e)


class DescribeTransferUser(ChildDescribeSource):

    def get_query(self):
        query = super().get_query()
        query.capture_parent_id = True
        return query

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('transfer')
        results = []
        for parent_id, user in resources:
            tu = self.manager.retry(
                client.describe_user, ServerId=parent_id,
                UserName=user['UserName']).get('User')
            results.append(tu)
        return results


@resources.register('transfer-user')
class TransferUser(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'transfer'
        arn = 'Arn'
        arn_type = 'user'
        enum_spec = ('list_users', 'Users', None)
        detail_spec_spec = ('describe_user', 'UserName', None)
        parent_spec = ('transfer-server', 'ServerId', True)
        name = id = 'UserName'
        cfn_type = 'AWS::Transfer::User'

    source_mapping = {
        'describe-child': DescribeTransferUser
    }

    def get_resources(self, ids, cache=True, augment=True):
        return super(TransferUser, self).get_resources(ids, cache, augment=False)


@TransferUser.action_registry.register('delete')
class DeleteUser(BaseAction):
    """Action to delete a Transfer User

    :example:

    .. code-block:: yaml

            policies:
              - name: transfer-user-delete
                resource: transfer-user
                actions:
                  - delete
    """
    schema = type_schema('delete')
    permissions = ("transfer:DeleteUser",)

    def process(self, resources):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_user, resources))

    def process_user(self, user):
        client = local_session(
            self.manager.session_factory).client('transfer')
        try:

            client.delete_user(
                ServerId=user['Arn'].split('/')[1],
                UserName=user['UserName'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting user:\n %s" % e)
