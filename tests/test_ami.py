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

import jmespath

from c7n.exceptions import ClientError
from .common import BaseTest


class TestAMI(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data("test_ami")
        p = self.load_policy(
            {
                "name": "test-ami",
                "resource": "ami",
                "filters": [
                    {"Name": "LambdaCompiler"}, {"type": "image-age", "days": 0.2}
                ],
                "actions": ["deregister"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_deregister_delete_snaps(self):
        factory = self.replay_flight_data('test_ami_deregister_delete_snap')
        p = self.load_policy({
            'name': 'deregister-snap',
            'resource': 'ami',
            'actions': [{
                'type': 'deregister',
                'delete-snapshots': True}]},
            session_factory=factory, config={'account_id': '644160558196'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('ec2')
        snap_ids = jmespath.search(
            'BlockDeviceMappings[].Ebs.SnapshotId', resources[0])
        self.assertRaises(
            ClientError, client.describe_snapshots, SnapshotIds=snap_ids, OwnerIds=['self'])

    def test_unused_ami_with_asg_launch_templates(self):
        factory = self.replay_flight_data('test_unused_ami_launch_template')
        p = self.load_policy(
            {"name": "test-unused-ami", "resource": "ami", "filters": ["unused"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ImageId'], 'ami-0515ff4f8f9dbeb31')

    def test_unused_ami_true(self):
        factory = self.replay_flight_data("test_unused_ami_true")
        p = self.load_policy(
            {"name": "test-unused-ami", "resource": "ami", "filters": ["unused"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_unused_ami_false(self):
        factory = self.replay_flight_data("test_unused_ami_false")
        p = self.load_policy(
            {
                "name": "test-unused-ami",
                "resource": "ami",
                "filters": [{"type": "unused", "value": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_ami_cross_accounts(self):
        session_factory = self.replay_flight_data("test_ami_cross_accounts")
        p = self.load_policy(
            {
                "name": "cross-account-ami",
                "resource": "ami",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
