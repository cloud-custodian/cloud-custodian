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


class ElasticSearch(BaseTest):

    def test_resource_manager(self):
        factory = self.replay_flight_data('test_elasticsearch_query')
        p = self.load_policy({
            'name': 'es-query',
            'resource': 'elasticsearch',
            'filters': [{'DomainName': 'indexme'}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DomainName'], 'indexme')

    def test_delete_search(self):
        factory = self.replay_flight_data('test_elasticsearch_delete')
        p = self.load_policy({
            'name': 'es-query',
            'resource': 'elasticsearch',
            'filters': [{'DomainName': 'indexme'}],
            'actions': ['delete']
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DomainName'], 'indexme')

        client = factory().client('es')

        state = client.describe_elasticsearch_domain(
            DomainName='indexme')['DomainStatus']
        self.assertEqual(state['Deleted'], True)

