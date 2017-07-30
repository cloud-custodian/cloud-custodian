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

from botocore.exceptions import ClientError

from c7n.credentials import SessionFactory, assumed_session
from c7n.version import version

from .common import BaseTest


class Credential(BaseTest):

    def test_session_factory(self):
        factory = SessionFactory('us-east-1')
        session = factory()
        self.assertTrue(
            session._session.user_agent().startswith(
                'CloudCustodian/%s' % version))

    def xtest_assumed_session(self):
        # placebo's datetime bug bites again
        # https://github.com/garnaat/placebo/pull/50
        factory = self.replay_flight_data('test_credential_sts')    
        user = factory().client('iam').get_user()
        session = assumed_session(
            "arn:aws:iam::644160558196:role/CloudCustodianRole",
            "custodian-dev",
            session=factory())
        try:
            session.client('iam').get_user()
        except ClientError as e:
            self.assertEqual(e.response['Error']['Code'], 'ValidationError')
        else:
            self.fail("sts user not identifyable this way")

        self.assertEqual(user['User']['UserName'], 'kapil')


