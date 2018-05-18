# Copyright 2018 Capital One Services, LLC
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


class TestSecretsManager(BaseTest):

    def test_secrets_manager_tag_resource(self):
        session = self.replay_flight_data("test_secrets_manager_tag")
        client = session(region="us-east-1").client("secretsmanager")
        p = self.load_policy(
            {
                "name": "secrets-manager-resource",
                "resource": "secrets-manager",
                "actions": [{"type": "tag", "key": "new-tag", "value": "new-value"}],
            },
            session_factory=session,
        )
        resources = p.run()
        self.assertFalse(resources[0].get('Tags'))

        p = self.load_policy(
            {
                "name": "secrets-manager-resource",
                "resource": "secrets-manager",
                "actions": [{"type": "remove-tag", "tags": ["new-tag"]}],
            },
            session_factory=session,
        )
        resources = p.run()
        self.assertEqual(resources[0]['Tags'][0]['Key'], 'new-tag')

        final_tags = client.describe_secret(SecretId="c7n-test-key").get("Tags")
        self.assertFalse(final_tags)

    def test_mark_secret_for_op(self):
        session = self.replay_flight_data("test_secrets_manager_mark_for_op")
        client = session(region="us-east-1").client("secretsmanager")
        p = self.load_policy(
            {
                "name": "secrets-manager-resource",
                "resource": "secrets-manager",
                "actions": [{"type": "mark-for-op", "op": "tag", "days": 1}],
            },
            session_factory=session,
        )
        resources = p.run()
        self.assertFalse(resources[0].get('Tags'))
        new_tags = client.describe_secret(SecretId="c7n-test-key").get("Tags")
        self.assertTrue("tag@" in new_tags[0].get("Value"))
