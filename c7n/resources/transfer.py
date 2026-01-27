# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.manager import resources
from concurrent.futures import as_completed
from c7n.query import QueryResourceManager, ChildResourceManager, TypeInfo, ChildDescribeSource
from c7n.utils import local_session, type_schema


@resources.register('transfer-server')
class TransferServer(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'transfer'
        enum_spec = ('list_servers', 'Servers', {'MaxResults': 60})
        detail_spec = (
            'describe_server', 'ServerId', 'ServerId', 'Server')
        id = name = 'ServerId'
        arn_type = "server"
        cfn_type = config_type = 'AWS::Transfer::Server'
        permissions_augment = ("transfer:ListTagsForResource",)


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

        client = local_session(
            self.manager.session_factory).client('transfer')
        with self.executor_factory(
                max_workers=min(3, len(resources) or 1)) as w:
            futures = {}
            for r in resources:
                futures[w.submit(self.process_server, client, r)] = r
            for f in as_completed(futures):
                r = futures[f]
                if f.exception():
                    self.log.warning(
                        "Exception stoping transfer server:%s error:\n%s",
                        r['ServerId'], f.exception())
                    continue

    def process_server(self, client, server):
        client.stop_server(ServerId=server['ServerId'])


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

        client = local_session(
            self.manager.session_factory).client('transfer')
        with self.executor_factory(
                max_workers=min(3, len(resources) or 1)) as w:
            futures = {}
            for r in resources:
                futures[w.submit(self.process_server, client, r)] = r
            for f in as_completed(futures):
                r = futures[f]
                if f.exception():
                    self.log.warning(
                        "Exception starting transfer server:%s error:\n%s",
                        r['ServerId'], f.exception())
                    continue

    def process_server(self, client, server):
        client.start_server(ServerId=server['ServerId'])


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
        client = local_session(
            self.manager.session_factory).client('transfer')
        with self.executor_factory(
                max_workers=min(3, len(resources) or 1)) as w:
            futures = {}
            for r in resources:
                futures[w.submit(self.process_server, client, r)] = r
            for f in as_completed(futures):
                r = futures[f]
                if f.exception():
                    self.log.warning(
                        "Exception deleting transfer server:%s error:\n%s",
                        r['ServerId'], f.exception())
                    continue

    def process_server(self, client, server):
        try:
            client.delete_server(ServerId=server['ServerId'])
        except client.exceptions.ResourceNotFoundException:
            pass


class DescribeTransferUser(ChildDescribeSource):

    def get_query(self):
        return super().get_query(capture_parent_id=True)

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
        detail_spec = ('describe_user', 'UserName', 'UserName', 'User')
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
        client = local_session(
            self.manager.session_factory).client('transfer')
        with self.executor_factory(
                max_workers=min(3, len(resources) or 1)) as w:
            futures = {}
            for r in resources:
                futures[w.submit(self.process_user, client, r)] = r
            for f in as_completed(futures):
                r = futures[f]
                if f.exception():
                    self.log.warning(
                        "Exception deleting transfer user:%s error:\n%s",
                        r['UserName'], f.exception())
                    continue

    def process_user(self, client, user):
        try:
            client.delete_user(
                ServerId=user['Arn'].split('/')[1],
                UserName=user['UserName'])
        except client.exceptions.ResourceNotFoundException:
            pass
