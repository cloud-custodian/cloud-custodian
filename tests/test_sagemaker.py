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
from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest


class TestNotebookInstance(BaseTest):
    def test_list_notebook_instances(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_notebook_instances')
        p = self.load_policy({
            'name': 'list-sagemaker-notebooks',
            'resource': 'sagemaker-notebook',
            'filters': [{
                'type': 'value',
                'key': 'SubnetId',
                'value': 'subnet-efbcccb7'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_tag_notebook_instances(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_tag_notebook_instances')
        p = self.load_policy({
            'name': 'tag-sagemaker-notebooks',
            'resource': 'sagemaker-notebook',
            'filters': [{
                'tag:Category': 'absent'}],
            'actions': [{
                'type': 'tag',
                'key': 'Category',
                'value': 'TestValue'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('sagemaker')
        tags = client.list_tags(
            ResourceArn=resources[0]['NotebookInstanceArn'])['Tags']
        self.assertEqual(tags[0]['Value'], 'TestValue')

    def test_remove_tag_notebook_instance(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_remove_tag_notebook_instances')
        p = self.load_policy({
            'name': 'untag-sagemaker-notebooks',
            'resource': 'sagemaker-notebook',
            'filters': [{
                'tag:Category': 'TestValue'}],
            'actions': [{
                'type': 'remove-tag',
                'tags': ['Category']}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('sagemaker')
        tags = client.list_tags(
            ResourceArn=resources[0]['NotebookInstanceArn'])['Tags']
        self.assertEqual(len(tags), 0)

    def test_mark_for_op_notebook_instance(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_mark_for_op_notebook_instance')
        p = self.load_policy({
            'name': 'sagemaker-notebooks-untagged-delete',
            'resource': 'sagemaker-notebook',
            'filters': [
                {'tag:Category': 'absent'},
                {'tag:custodian_cleanup': 'absent'},
                {'NotebookInstanceStatus': 'InService'}],
            'actions': [{
                'type': 'mark-for-op',
                'tag': 'custodian_cleanup',
                'op': 'stop',
                'days': 1}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('sagemaker')
        tags = client.list_tags(
            ResourceArn=resources[0]['NotebookInstanceArn'])['Tags']
        self.assertTrue(tags[0]['Key'], 'custodian_cleanup')

    def test_marked_for_op_notebook_instance(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_marked_for_op_notebook_instance')
        p = self.load_policy({
            'name': 'sagemaker-notebooks-untagged-delete',
            'resource': 'sagemaker-notebook',
            'filters': [{
                'type': 'marked-for-op',
                'tag': 'custodian_cleanup',
                'op': 'stop',
                'skew': 1}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_start_notebook_instance(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_start_notebook_instance')
        p = self.load_policy({
            'name': 'start-sagemaker-notebook',
            'resource': 'sagemaker-notebook',
            'actions': [{'type': 'start'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertTrue(len(resources), 1)

        client = session_factory().client('sagemaker')
        notebook = client.describe_notebook_instance(
            NotebookInstanceName=resources[0]['NotebookInstanceName'])
        self.assertTrue(notebook['NotebookInstanceStatus'], 'Pending')

    def test_stop_notebook_instance(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_stop_notebook_instance')
        p = self.load_policy({
            'name': 'stop-invalid-sagemaker-notebook',
            'resource': 'sagemaker-notebook',
            'filters': [
                {'tag:Category': 'absent'}],
            'actions': [{'type': 'stop'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertTrue(len(resources), 1)

        client = session_factory().client('sagemaker')
        notebook = client.describe_notebook_instance(
            NotebookInstanceName=resources[0]['NotebookInstanceName'])
        self.assertTrue(notebook['NotebookInstanceStatus'], 'Stopping')

    def test_delete_notebook_instance(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_delete_notebook_instance')
        p = self.load_policy({
            'name': 'delete-unencrypted-sagemaker-notebook',
            'resource': 'sagemaker-notebook',
            'filters': [{'KmsKeyId': 'empty'}],
            'actions': [{'type': 'delete'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertTrue(len(resources), 1)

        client = session_factory().client('sagemaker')
        notebook = client.describe_notebook_instance(
            NotebookInstanceName=resources[0]['NotebookInstanceName'])
        self.assertTrue(notebook['NotebookInstanceStatus'], 'Deleting')


class TestSagemakerJob(BaseTest):
    def test_list_jobs(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_training_jobs')
        p = self.load_policy({
            'name': 'list-training-jobs',
            'filters': [{
                'TrainingJobStatus': 'Completed'}],
            'resource': 'sagemaker-job'
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_stop_job(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_training_job_stop')
        p = self.load_policy({
            'name': 'stop-training-job',
            'resource': 'sagemaker-job',
            'filters': [
                {'TrainingJobStatus': 'InProgress'},
                {'type': 'value',
                 'key': 'InputDataConfig[].ChannelName',
                 'value': 'train',
                 'op': 'contains'}],
            'actions': [{
                'type': 'stop'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertTrue(len(resources), 1)
        client = session_factory(region='us-east-1').client('sagemaker')
        status = client.describe_training_job(
            TrainingJobName='kmeans-2018-01-18-19-21-19-098'
        )['TrainingJobStatus']
        self.assertEqual(status, 'Stopping')


class TestSagemakerEndpoint(BaseTest):

    def test_sagemaker_endpoints(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_endpoints')
        p = self.load_policy({
            'name': 'list-endpoints',
            'resource': 'sagemaker-endpoint',
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_sagemaker_endpoint_delete(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_endpoint_delete')
        client = session_factory(region='us-east-1').client('sagemaker')
        p = self.load_policy({
            'name': 'delete-endpoint-by-config',
            'resource': 'sagemaker-endpoint',
            'filters': [{
                'EndpointConfigName': 'kmeans-2018-01-18-19-25-36-887'
            }],
            'actions': [{
                'type': 'delete'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        status = client.describe_endpoint(
            EndpointName=resources[0]['EndpointName'])['EndpointStatus']
        self.assertEqual(status, 'Deleting')


class TestSagemakerEndpointConfig(BaseTest):

    def test_sagemaker_endpoint_config(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_endpoint_config')
        p = self.load_policy({
            'name': 'list-endpoint-configs',
            'resource': 'sagemaker-endpoint-config'
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_sagemaker_endpoint_config_delete(self):
        session_factory = self.replay_flight_data(
            'test_sagemaker_endpoint_config_delete')
        client = session_factory(region='us-east-1').client('sagemaker')
        p = self.load_policy({
            'name': 'delete-endpoint-config',
            'resource': 'sagemaker-endpoint-config',
            'filters': [{
                'type': 'value',
                'key': 'ProductionVariants[].InstanceType',
                'value': 'ml.m4.xlarge',
                'op': 'contains'}],
            'actions': [{
                'type': 'delete'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        configs = client.list_endpoint_configs()['EndpointConfigs']
        self.assertEqual(len(configs), 0)
