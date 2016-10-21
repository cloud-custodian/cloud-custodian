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
from boto3.session import Session
from common import BaseTest
from c7n.credentials import assumed_session
from c7n.credentials import SessionFactory


TEST_PROFILE = 'default'
TEST_REGION = 'us-east-1'

class CredentialsTest(BaseTest):

    def test_session_factory(self):
        session_factory = SessionFactory(
            TEST_REGION,
            TEST_PROFILE,
            # 'role:arn',
        )
        session = session_factory()
        self.assertIsInstance(session, Session)
        self.assertEqual(TEST_PROFILE, session.profile_name)
        self.assertEqual(TEST_REGION, session.region_name)
