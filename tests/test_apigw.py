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


class TestRestStage(BaseTest):

    def test_rest_stage_resource(self):
        session_factory = self.replay_flight_data('test_rest_stage')

        p = self.load_policy({
            'name': 'all-rest-stages',
            'resource': 'rest-stage',
            'filters': [
                {'tag:ENV': "DEV"}
                ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['stageName'], 'latest')
