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


from common import BaseTest

class CloudFront(BaseTest):

    def test_distribution_metric_filter(self):
        factory = self.replay_flight_data('test_distribution_metric_filter')
        p = self.load_policy({
            'name': 'requests-filter',
            'resource': 'distribution',
            'filters': [{
                'type': 'metrics',
                'name': 'Requests',
                'value': 3,
                'op': 'ge'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(
            resources[0]['DomainName'], 'd1k7b41j4nj6pa.cloudfront.net')
