# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, ChildResourceManager, TypeInfo
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
class StopServer(BaseAction):
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
                "Exception stopping server:\n %s" % e)


@TransferServer.action_registry.register('delete')
class StopServer(BaseAction):
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
                "Exception stopping server:\n %s" % e)

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

    def get_resources(self, ids, cache=True, augment=True):
        return super(TransferUser, self).get_resources(ids, cache, augment=False)

