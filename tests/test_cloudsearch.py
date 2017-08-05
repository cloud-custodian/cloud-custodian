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


from .common import BaseTest


class CloudSearch(BaseTest):

    def test_resource_manager(self):
        factory = self.replay_flight_data('test_cloudsearch_query')
        p = self.load_policy({
            'name': 'cs-query',
            'resource': 'cloudsearch',
            'filters': [{'DomainName': 'sock-index'}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DomainName'], 'sock-index')

    def test_delete_search(self):
        factory = self.replay_flight_data('test_cloudsearch_delete')
        p = self.load_policy({
            'name': 'csdel',
            'resource': 'cloudsearch',
            'filters': [{'DomainName': 'sock-index'}],
            'actions': ['delete']
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('cloudsearch')
        state = client.describe_domains(
            DomainNames=['sock-index'])['DomainStatusList'][0]
        self.assertEqual(state['Deleted'], True)
