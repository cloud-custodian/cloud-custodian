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


class TestAMI(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('test_ami')
        p = self.load_policy({
            'name': 'test-ami',
            'resource': 'ami',
            'filters': [
                {'Name': 'LambdaCompiler'},
                {'type': 'image-age', 'days': 0.2}],
            'actions': ['deregister']
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
