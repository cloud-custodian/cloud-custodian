# Copyright 2019 Capital One Services, LLC
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


class BackupTest(BaseTest):

    def test_augment(self):
        factory = self.replay_flight_data("test_backup_augment")
        p = self.load_policy({
            'name': 'all-backup',
            'resource': 'aws.backup-plan'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        plan = resources.pop()
        self.assertEqual(
            plan['Tags'],
            [{'Key': 'App', 'Value': 'Backups'}])
        self.assertTrue('Rules' in plan)

        self.assertEqual(
            p.resource_manager.get_arns([plan]),
            [plan['BackupPlanArn']])
        resources = p.resource_manager.get_resources([plan['BackupPlanId']])
        self.assertEqual(len(resources), 1)


class BackupPlanTest(BaseTest):

    def test_backup_plan_tag_untag(self):
        factory = self.replay_flight_data("test_backup_plan_tag_untag")
        p = self.load_policy(
            {
                "name": "backup-plan-tag",
                "resource": "backup-plan",
                "filters": [{"tag:target-tag": "present"}],
                "actions": [
                    {"type": "remove-tag", "tags": ["target-tag"]},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("backup")
        tag = client.list_tags(ResourceArn=resources[0]['BackupPlanArn'])
        self.assertEqual(len(tag.get('Tags')), 0)
