# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.manager import resources
from concurrent.futures import as_completed
from c7n.query import QueryResourceManager, ChildResourceManager, TypeInfo, ChildDescribeSource
from c7n.utils import local_session, type_schema, chunks


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

        futures = []
        client = local_session(
            self.manager.session_factory).client('transfer')
        with self.executor_factory(max_workers=2) as w:
            for server_set in chunks(resources, size=5):
                futures.append(w.submit(self.process_server_set, client, server_set))
            for f in as_completed(futures):
                r = futures[f]
                if f.exception():
                    self.log.error(
                        "Exception stopping transfer server %s:\n %s",
                        r['ServerId'], f.exception())

    def process_server_set(self, client, server_set):
        for s in server_set:
            client.stop_server(ServerId=s['ServerId'])


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

        futures = []
        client = local_session(
            self.manager.session_factory).client('transfer')
        with self.executor_factory(max_workers=2) as w:
            for server_set in chunks(resources, size=5):
                futures.append(w.submit(self.process_server_set, client, server_set))
            for f in as_completed(futures):
                r = futures[f]
                if f.exception():
                    self.log.error(
                        "Exception starting transfer server %s:\n %s",
                        r['ServerId'], f.exception())

    def process_server_set(self, client, server_set):
        for s in server_set:
            client.start_server(ServerId=s['ServerId'])


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
        futures = []
        client = local_session(
            self.manager.session_factory).client('transfer')
        with self.executor_factory(max_workers=2) as w:
            for server_set in chunks(resources, size=5):
                futures.append(w.submit(self.process_server_set, client, server_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting transfer server \n %s",
                        f.exception())

    def process_server_set(self, client, server_set):
        for s in server_set:
            try:
                client.delete_server(ServerId=s['ServerId'])
            except client.exceptions.NotFoundException:
                pass


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
        futures = []
        client = local_session(
            self.manager.session_factory).client('transfer')
        with self.executor_factory(max_workers=2) as w:
            for user_set in chunks(resources, size=5):
                futures.append(w.submit(self.process_user_set, client, user_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting transfer user \n %s",
                        f.exception())

    def process_user_set(self, client, user_set):
        for u in user_set:
            try:
                client.delete_user(
                    ServerId=u['Arn'].split('/')[1],
                    UserName=u['UserName'])
            except client.exceptions.NotFoundException:
                pass
