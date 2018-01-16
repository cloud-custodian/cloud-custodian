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
            'resource': 'sagemaker-notebook'
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
            'name': 'delete-invalid-sagemaker-notebook',
            'resource': 'sagemaker-notebook',
            'filters': [
                {'tag:DeleteMe': 'present'}],
            'actions': [{'type': 'delete'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertTrue(len(resources), 1)

        client = session_factory().client('sagemaker')
        notebook = client.describe_notebook_instance(
            NotebookInstanceName=resources[0]['NotebookInstanceName'])
        self.assertTrue(notebook['NotebookInstanceStatus'], 'Deleting')
