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


class SimpleDB(BaseTest):

    def test_delete(self):
        session_factory = self.replay_flight_data('test_simpledb_delete')
        p = self.load_policy({
            'name': 'sdb-del',
            'resource': 'simpledb',
            'filters': [
                {'DomainName': 'supersuper'}],
            'actions': ['delete']
        }, session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DomainName'], 'supersuper')
        extant_domains = session_factory().client(
            'sdb').list_domains()['DomainNames']
        self.assertTrue(
            resources[0]['DomainName'] not in extant_domains)

    def test_simpledb(self):
        session_factory = self.replay_flight_data('test_simpledb_query')
        p = self.load_policy({
            'name': 'sdbtest',
            'resource': 'simpledb'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DomainName'], 'devtest')
