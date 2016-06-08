# Copyright 2016 Capital One Services, LLC
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
import logging

from .common import BaseTest
from c7n.resources.ebs import (
    CopyInstanceTags, EncryptInstanceVolumes)
from c7n.executor import MainThreadExecutor


logging.basicConfig(level=logging.DEBUG)


class SnapshotTrimTest(BaseTest):

    def test_snapshot_trim(self):
        factory = self.replay_flight_data('test_ebs_snapshot_delete')
        p = self.load_policy({
            'name': 'snapshot-trim',
            'resource': 'ebs-snapshot',
            'filters': [
                {'tag:InstanceId': 'not-null'}],
            'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class AttachedInstanceTest(BaseTest):

    def test_ebs_instance_filter(self):
        factory = self.replay_flight_data('test_ebs_instance_filter')
        p = self.load_policy({
            'name': 'attached-instance-test',
            'resource': 'ebs',
            'filters': [
                {'type': 'instance',
                 'key': 'tag:Name',
                 'value': 'CompiledLambda'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class CopyInstanceTagsTest(BaseTest):

    def test_copy_instance_tags(self):
        # More a functional/coverage test then a unit test.        
        self.patch(
            CopyInstanceTags, 'executor_factory', MainThreadExecutor)
        factory = self.replay_flight_data('test_ebs_copy_instance_tags')
            
        volume_id = 'vol-2b047792'
    
        results = factory().client('ec2').describe_tags(
            Filters=[{'Name': 'resource-id', 'Values': [volume_id]}])['Tags']
        tags = {t['Key']: t['Value'] for t in results}
        self.assertEqual(tags, {})
        
        policy = self.load_policy({
            'name': 'test-copy-instance-tags',
            'resource': 'ebs',
            'actions': [{
                'type': 'copy-instance-tags',
                'tags': ['Name']}]},
            config={'region': 'us-west-2'},
            session_factory=factory)

        resources = policy.run()
        results = factory().client('ec2').describe_tags(
            Filters=[{'Name': 'resource-id', 'Values': [volume_id]}])['Tags']
        
        tags = {t['Key']: t['Value'] for t in results}
        self.assertEqual(tags['Name'], 'CompileLambda')

            
class EncryptExtantVolumesTest(BaseTest):

    def test_encrypt_volumes(self):
        self.patch(
            EncryptInstanceVolumes, 'executor_factory', MainThreadExecutor)
        output = self.capture_logging(level=logging.DEBUG)

        session_factory = self.replay_flight_data('test_encrypt_volumes')
        
        policy = self.load_policy({
            'name': 'ebs-remediate-attached',
            'resource': 'ebs',
            'filters': [
                {'Encrypted': False},                
                {'VolumeId': 'vol-fdd1f844'}],
            'actions': [
                {'type': 'encrypt-instance-volumes',
                 'delay': 0.1,
                 'key': 'alias/ebs/crypto'}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['Encrypted'], False)
