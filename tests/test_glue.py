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

from .common import BaseTest


class TestGlueConnections(BaseTest):

    def test_connections_query(self):
        session_factory = self.replay_flight_data("test_glue_query_resources")
        p = self.load_policy(
            {"name": "list-glue-connections", "resource": "glue-connection"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connection_subnet_filter(self):
        session_factory = self.replay_flight_data("test_glue_subnet_filter")
        p = self.load_policy(
            {
                "name": "glue-connection",
                "resource": "glue-connection",
                "filters": [
                    {"type": "subnet", "key": "tag:Name", "value": "Default-48"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(
            resources[0]["PhysicalConnectionRequirements"]["SubnetId"],
            "subnet-3a334610",
        )

    def test_connection_sg_filter(self):
        session_factory = self.replay_flight_data("test_glue_sg_filter")
        p = self.load_policy(
            {
                "name": "glue-connection",
                "resource": "glue-connection",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(
            resources[0]["PhysicalConnectionRequirements"]["SecurityGroupIdList"],
            ["sg-6c7fa917"],
        )

    def test_connection_delete(self):
        session_factory = self.replay_flight_data("test_glue_delete_connection")
        p = self.load_policy(
            {
                "name": "glue-connection",
                "resource": "glue-connection",
                "filters": [{"ConnectionType": "JDBC"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        connections = client.get_connections()["ConnectionList"]
        self.assertFalse(connections)
