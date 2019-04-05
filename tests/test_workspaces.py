# Copyright 2019 Capital One Services, LLC
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
from c7n.executor import MainThreadExecutor
from c7n.resources.workspaces import Workspace


class WorkspacesTest(BaseTest):

    def test_workspaces_query(self):
        session_factory = self.replay_flight_data("test_workspaces_query")
        p = self.load_policy(
            {
                "name": "workspaces-query-test",
                "resource": "workspaces"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_workspaces_tags(self):
        self.patch(Workspace, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_workspaces_query")
        p = self.load_policy(
            {
                "name": "workspaces-tag-test",
                "resource": "workspaces",
                "filters": [
                    {"tag:Environment": "sandbox"}
                ]
            },
            config={'account_id': '644160558196'},
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
