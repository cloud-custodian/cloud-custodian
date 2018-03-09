# Copyright 2017 Capital One Services, LLC
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

from .common import BaseTest


class ReplInstance(BaseTest):
    def test_describe_augment_no_tags(self):
        session_factory = self.replay_flight_data(
            'test_dms_repl_instance_describe_sans_tags')
        p = self.load_policy({
            'name': 'dms-replinstance',
            'resource': 'dms-instance'},
            session_factory=session_factory)        
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ReplicationInstanceIdentifier'],
                         'replication-instance-1')

    def test_describe_get_resources(self):
        session_factory = self.replay_flight_data(
            'test_dms_repl_instance_delete')
        p = self.load_policy({
            'name': 'dms-replinstance',
            'resource': 'dms-instance'},
            session_factory=session_factory)        
        resources = p.resource_manager.get_resources(
            ['replication-instance-1'])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ReplicationInstanceIdentifier'],
                         'replication-instance-1')        

    def test_delete(self):
        session_factory = self.replay_flight_data(
            'test_dms_repl_instance_delete')
        client = session_factory().client('dms')
        p = self.load_policy({
            'name': 'dms-replinstance',
            'resource': 'dms-instance',
            'actions': ['delete']},
            session_factory=session_factory)        
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ReplicationInstanceIdentifier'],
                         'replication-instance-1')
        instances = client.describe_replication_instances().get(
            'ReplicationInstances')
        self.assertEqual(instances[0]['ReplicationInstanceStatus'], 'deleting')


class ReplicationInstanceTagging(BaseTest):
    def test_replication_instance_tag(self):
        session_factory = self.replay_flight_data('test_dms_tag')
        p = self.load_policy({
            'name': 'tag-dms-instance',
            'resource': 'dms-instance',
            'filters': [{
                'tag:RequiredTag': 'absent'}],
            'actions': [{
                'type': 'tag',
                'key': 'RequiredTag',
                'value': 'RequiredValue'
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('dms')
        tag_list = client.list_tags_for_resource(
            ResourceArn=resources[0]['ReplicationInstanceArn'])['TagList']
        tag_value = [t['Value'] for t in tag_list if t['Key'] == 'RequiredTag']
        self.assertEqual(tag_value[0], 'RequiredValue')

    def test_remove_replication_instance_tag(self):
        session_factory = self.replay_flight_data('test_dms_tag_remove')
        p = self.load_policy({
            'name': 'remove-dms-tag',
            'resource': 'dms-instance',
            'filters': [{
                'tag:RequiredTag': 'RequiredValue'}],
            'actions': [{
                'type': 'remove-tag',
                'tags': ["RequiredTag"]
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('dms')
        tag_list = client.list_tags_for_resource(
           ResourceArn=resources[0]['ReplicationInstanceArn'])['TagList']
        self.assertFalse([t for t in tag_list if t['Key'] == 'RequiredTag'])

    def test_replication_instance_markforop(self):
        session_factory = self.replay_flight_data('test_dms_mark_for_op')
        p = self.load_policy({
            'name': 'dms-instance-markforop',
            'resource': 'dms-instance',
            'filters': [{
                'tag:RequiredTag': 'absent'}],
            'actions': [{
                'type': 'mark-for-op',
                'tag': 'custodian_cleanup',
                'op': 'delete',
                'days': 2}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('dms')
        tag_list = client.list_tags_for_resource(
            ResourceArn=resources[0]['ReplicationInstanceArn'])['TagList']
        self.assertTrue(
            [t['Value'] for t in tag_list if t['Key'] == 'custodian_cleanup'])

    def test_replication_instance_markedforop(self):
        session_factory = self.replay_flight_data('test_dms_marked_for_op')
        p = self.load_policy({
            'name': 'dms-instance-markedforop',
            'resource': 'dms-instance',
            'filters': [{
                'type': 'marked-for-op',
                'tag': 'custodian_cleanup',
                'op': 'delete',
                'skew': 2}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['ReplicationInstanceIdentifier'],
            'replication-instance-1')


class DmsEndpointTests(BaseTest):

    def test_resource_query(self):
        session_factory = self.replay_flight_data('test_dms_resource_query')
        p = self.load_policy({
            'name': 'dms-endpoint-query',
            'resource': 'dms-endpoint'}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_endpoint_modify_1(self):
        session_factory = self.replay_flight_data('test_dms_modify_endpoint_1')
        p = self.load_policy({
            'name': 'dms-sql-ssl',
            'resource': 'dms-endpoint',
            'filters': [
                {'EndpointIdentifier': 'c7n-test-dms-ep'},
                {'SslMode': 'none'}
            ],
            'actions': [{
                'type': 'modify-endpoint',
                'port': 3305,
                'sslmode': 'require'
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('dms')
        endpoint = client.describe_endpoints()['Endpoints'][0]
        self.assertEqual(endpoint['SslMode'], 'require')
        self.assertEqual(endpoint['Port'], 3305)

    def test_endpoint_modify_2(self):
        session_factory = self.replay_flight_data('test_dms_modify_endpoint_2')
        p = self.load_policy({
            'name': 'dms-s3-bucket',
            'resource': 'dms-endpoint',
            'filters': [
                {'EndpointIdentifier': 'c7n-s3-dms-ep'},
                {'S3Settings.BucketFolder': 'absent'}
            ],
            'actions': [{
                'type': 'modify-endpoint',
                's3settings': {
                    'bucketname': 'c7n-sm-test',
                    'bucketfolder': 's3_dms'}
                }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('dms')
        endpoint = client.describe_endpoints()['Endpoints'][0]
        self.assertEqual(endpoint['S3Settings']['BucketFolder'], 's3_dms')

    def test_endpoint_modify_3(self):
        session_factory = self.replay_flight_data('test_dms_modify_endpoint_3')
        p = self.load_policy({
            'name': 'dms-mongodb-nesting',
            'resource': 'dms-endpoint',
            'filters': [
                {'EndpointIdentifier': 'c7n-dms-mdb-ep'},
                {'MongoDbSettings.NestingLevel': 'one'}
            ],
            'actions': [{
                'type': 'modify-endpoint',
                'mongodbsettings': {'nestinglevel': 'none'}
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('dms')
        endpoint = client.describe_endpoints()['Endpoints'][0]
        self.assertEqual(
            endpoint['MongoDbSettings']['NestingLevel'], 'none')

    def test_endpoint_modify_4(self):
        session_factory = self.replay_flight_data('test_dms_modify_endpoint_4')
        p = self.load_policy({
            'name': 'dms-sql-auth',
            'resource': 'dms-endpoint',
            'filters': [
                {'EndpointIdentifier': 'c7n-dms-sql-ep'},
                {'Username': 'madmin'}
            ],
            'actions': [{
                'type': 'modify-endpoint',
                'username': 'madmin1',
                'password': 'generic_password'
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('dms')
        endpoint = client.describe_endpoints()['Endpoints'][0]
        self.assertEqual(endpoint['Username'], 'madmin1')
