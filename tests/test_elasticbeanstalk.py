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

import datetime
from dateutil.parser import parse as date_parse

from .common import BaseTest, Config
from .test_offhours import mock_datetime_now


class ElasticBeanstalkEnvironment(BaseTest):

    def test_resource_manager(self):
        config = Config.empty(account_id='012345678901')
        factory = self.replay_flight_data('test_elasticbeanstalk_describe_envs')
        p = self.load_policy({
            'name': 'eb-env-query',
            'resource': 'elasticbeanstalk-environment',
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 4)

    def test_eb_env_regex(self):
        config = Config.empty(account_id='012345678901')
        factory = self.replay_flight_data('test_elasticbeanstalk_describe_envs')
        p = self.load_policy({
            'name': 'eb-find-inactive',
            'resource': 'elasticbeanstalk-environment',
            'filters': [
                {
                    'type': 'value',
                    'key': 'CNAME',
                    'op': 'regex',
                    'value': '.*inactive.*',
                    }
                ],
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_eb_env_uptime(self):
        config = Config.empty(account_id='012345678901')
        factory = self.replay_flight_data('test_elasticbeanstalk_describe_envs')
        p = self.load_policy({
            'name': 'eb-find-inactive',
            'resource': 'elasticbeanstalk-environment',
            'filters': [
                {
                    'type': 'value',
                    'key': 'DateCreated',
                    'value': 1,
                    'value_type': 'age',
                    'op': 'greater-than',
                    }
                ],
            }, session_factory=factory)
        with mock_datetime_now(date_parse('2017-10-19'), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 2)

