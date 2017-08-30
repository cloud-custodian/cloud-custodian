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


class UserPool(BaseTest):

    def test_query_user_pool(self):
        factory = self.replay_flight_data('test_cognito-user-pool')
        p = self.load_policy({
            'name': 'users',
            'resource': 'user-pool'
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(
            sorted([n['Name'] for n in resources]),
            ['c7nusers', 'origin_userpool_MOBILEHUB_1667653900'])
