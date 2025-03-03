from botocore.exceptions import ClientError
import time

from .common import BaseTest
from c7n.utils import local_session


class TestKeyspace(BaseTest):

    def test_keyspace_tags(self):
        factory = self.replay_flight_data('test_keyspace_tag')
        p = self.load_policy({
            'name': 'keyspace-tag',
            'resource': 'keyspace',
            'actions': [
                {'type': 'tag',
                 'tags': {'TestTag': 'c7n'}},]},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('keyspaces')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['resourceArn'])["tags"]
        self.assertEqual(tags[0]["key"], "TestTag")

        p = self.load_policy({
            'name': 'keyspace-untag',
            'resource': 'keyspace',
            'filters': [{"tag:TestTag": "c7n"}],
            'actions': [
                {'type': 'remove-tag',
                 'tags': ["TestTag"]},]},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceArn=resources[0]['resourceArn'])["tags"]
        self.assertEqual(len(tags), 0)

    def test_keyspace_update(self):
        factory = self.replay_flight_data('test_keyspace_update')
        client = local_session(factory).client('keyspaces')
        p = self.load_policy({
            'name': 'keyspace-update',
            'resource': 'keyspace',
            'filters': [{'keyspaceName': 'c7n_test'}],
            'actions': [
                {'type': 'update',
                 'replicationSpecification': {
                     'replicationStrategy': 'MULTI_REGION',
                     'regionList': ['us-east-1', 'us-west-2']}, }]},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)
        keyspace = client.get_keyspace(keyspaceName=resources[0]['keyspaceName'])
        self.assertEqual(keyspace['replicationStrategy'], 'MULTI_REGION')
        self.assertEqual(keyspace['replicationRegions'], ['us-east-1', 'us-west-2'])

    def test_keyspace_delete(self):
        factory = self.replay_flight_data('test_keyspace_delete')
        p = self.load_policy({
            'name': 'keyspace-delete',
            'resource': 'keyspace',
            'filters': [{'keyspaceName': 'c7n_test'}],
            'actions': ['delete']},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('keyspaces')
        if self.recording:
            time.sleep(45)
        with self.assertRaises(ClientError):
            client.get_keyspace(keyspaceName=resources[0]['keyspaceName'])


class TestKeyspaceTable(BaseTest):

    def test_keyspace_table_tags(self):
        factory = self.replay_flight_data('test_keyspace_table_tag')
        p = self.load_policy({
            'name': 'keyspace-table-tag',
            'resource': 'keyspace-table',
            'actions': [
                {'type': 'tag',
                 'tags': {'TestTag': 'c7n'}},]},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('keyspaces')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['resourceArn'])["tags"]
        self.assertEqual(tags[0]["key"], "TestTag")

        p = self.load_policy({
            'name': 'keyspace-table-untag',
            'resource': 'keyspace-table',
            'filters': [{"tag:TestTag": "c7n"}],
            'actions': [
                {'type': 'remove-tag',
                 'tags': ["TestTag"]},]},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceArn=resources[0]['resourceArn'])["tags"]
        self.assertEqual(len(tags), 0)

    def test_keyspace_table_update(self):
        factory = self.replay_flight_data('test_keyspace_table_update')
        client = local_session(factory).client('keyspaces')
        p = self.load_policy({
            'name': 'keyspace-table-update',
            'resource': 'keyspace-table',
            'filters': [{'tableName': 'c7n_test_table'}],
            'actions': [
                {'type': 'update',
                 'pointInTimeRecovery': {
                     'status': 'DISABLED'}}]},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)
        keyspace_table = client.get_table(
            keyspaceName=resources[0]['keyspaceName'],
            tableName=resources[0]['tableName']
        )
        self.assertEqual(keyspace_table['pointInTimeRecovery']['status'], 'DISABLED')

    def test_keyspace_table_delete(self):
        factory = self.replay_flight_data('test_keyspace_table_delete')
        p = self.load_policy({
            'name': 'keyspace-table-delete',
            'resource': 'keyspace-table',
            'filters': [{'tableName': 'c7n_test_table'}],
            'actions': ['delete']},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('keyspaces')
        if self.recording:
            time.sleep(45)
        with self.assertRaises(ClientError):
            client.get_table(
                keyspaceName=resources[0]['keyspaceName'],
                tableName=resources[0]['tableName']
            )
