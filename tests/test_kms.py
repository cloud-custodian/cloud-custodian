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
from common import BaseTest


class KMSTest(BaseTest):

    def test_kms_grant(self):
        session_factory = self.replay_flight_data('test_kms_grants')
        p = self.load_policy(
            {'name': 'kms-grant-count',
             'resource': 'kms',
             'filters': [
                 {'type': 'grant-count'}]},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_key_rotation(self):
        session_factory = self.replay_flight_data('test_key_rotation')
        p = self.load_policy(
            {'name': 'kms-key-rotation',
             'resource': 'kms-key',
             'filters': [
                 {'type': 'key-rotation-status', 'key': 'KeyRotationEnabled',
                  'value': False}]},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 7)
