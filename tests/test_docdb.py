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

from .common import BaseTest, TestConfig as Config

from nose.tools import set_trace

class docdbTest(BaseTest):

    def test_docdb_delete(self): 
        session_factory = self.record_flight_data("test_docdb_delete")
        p = self.load_policy(
            {
                "name": "docdb-delete",
                "resource": "docdb",
                "filters": [{"tag:Owner": "test"}],
                "actions": [{"type": "delete", "skip-snapshot": True}],
            },
            config=Config.empty(),
            session_factory=session_factory,
        )
        resources = p.run()
        set_trace() 
        self.assertEqual(len(resources), 1)