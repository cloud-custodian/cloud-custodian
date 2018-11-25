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

from .common import BaseTest, functional
from botocore.exceptions import ClientError


class RDSParamGroupTest(BaseTest):

    @functional
    def test_rdsparamgroup_delete(self):
        session_factory = self.replay_flight_data("test_rdsparamgroup_delete")
        client = session_factory().client("rds")

        name = "pg-test"

        # Create the PG
        client.create_db_parameter_group(
            DBParameterGroupName=name,
            DBParameterGroupFamily="mysql5.5",
            Description="test",
        )

        # Ensure it exists
        ret = client.describe_db_parameter_groups(DBParameterGroupName=name)
        self.assertEqual(len(ret["DBParameterGroups"]), 1)

        # Delete it via custodian
        p = self.load_policy(
            {
                "name": "rdspg-delete",
                "resource": "rds-param-group",
                "filters": [{"DBParameterGroupName": name}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify it is gone
        try:
            client.describe_db_parameter_groups(DBParameterGroupName=name)
        except ClientError:
            pass
        else:
            self.fail("parameter group {} still exists".format(name))
            self.addCleanup(client.delete_db_parameter_group, DBParameterGroupName=name)

    @functional
    def test_rdsparamgroup_copy(self):
        session_factory = self.replay_flight_data("test_rdsparamgroup_copy")
        client = session_factory().client("rds")

        name = "pg-orig"
        copy_name = "pg-copy"

        # Create the PG
        client.create_db_parameter_group(
            DBParameterGroupName=name,
            DBParameterGroupFamily="mysql5.5",
            Description="test",
        )
        self.addCleanup(client.delete_db_parameter_group, DBParameterGroupName=name)

        # Copy it via custodian
        p = self.load_policy(
            {
                "name": "rdspg-copy",
                "resource": "rds-param-group",
                "filters": [{"DBParameterGroupName": name}],
                "actions": [{"type": "copy", "name": copy_name}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Ensure it exists
        ret = client.describe_db_parameter_groups(DBParameterGroupName=copy_name)
        self.assertEqual(len(ret["DBParameterGroups"]), 1)
        self.addCleanup(
            client.delete_db_parameter_group, DBParameterGroupName=copy_name
        )

    @functional
    def test_rdsparamgroup_modify(self):
        session_factory = self.replay_flight_data("test_rdsparamgroup_modify")
        client = session_factory().client("rds")

        name = "pg-test"

        # Create the PG
        client.create_db_parameter_group(
            DBParameterGroupName=name,
            DBParameterGroupFamily="mysql5.5",
            Description="test",
        )
        self.addCleanup(client.delete_db_parameter_group, DBParameterGroupName=name)

        # Modify it via custodian
        p = self.load_policy(
            {
                "name": "rdspg-modify",
                "resource": "rds-param-group",
                "filters": [{"DBParameterGroupName": name}],
                "actions": [
                    {
                        "type": "modify",
                        "params": [
                            {"name": "autocommit", "value": "0"},
                            {"name": "automatic_sp_privileges", "value": "1"},
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Ensure that params were set
        ret = client.describe_db_parameters(DBParameterGroupName=name)
        count = 0
        for param in ret["Parameters"]:
            if param["ParameterName"] == "autocommit":
                self.assertEqual(param["ParameterValue"], "0")
                count += 1
            elif param["ParameterName"] == "automatic_sp_privileges":
                self.assertEqual(param["ParameterValue"], "1")
                count += 1
            if count == 2:
                break
        self.assertEqual(count, 2)


class RDSClusterParamGroupTest(BaseTest):

    @functional
    def test_rdsclusterparamgroup_delete(self):
        session_factory = self.replay_flight_data("test_rdsclusterparamgroup_delete")
        client = session_factory().client("rds")

        name = "pg-cluster-test"

        # Create the PG
        client.create_db_cluster_parameter_group(
            DBClusterParameterGroupName=name,
            DBParameterGroupFamily="aurora5.6",
            Description="test",
        )

        # Ensure it exists
        ret = client.describe_db_cluster_parameter_groups(
            DBClusterParameterGroupName=name
        )
        self.assertEqual(len(ret["DBClusterParameterGroups"]), 1)

        # Delete it via custodian
        p = self.load_policy(
            {
                "name": "rdspgc-delete",
                "resource": "rds-cluster-param-group",
                "filters": [{"DBClusterParameterGroupName": name}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify it is gone
        try:
            client.describe_db_cluster_parameter_groups(
                DBClusterParameterGroupName=name
            )
        except ClientError:
            pass
        else:
            self.fail("parameter group cluster {} still exists".format(name))
            self.addCleanup(
                client.delete_db_cluster_parameter_group,
                DBClusterParameterGroupName=name,
            )

    @functional
    def test_rdsclusterparamgroup_copy(self):
        session_factory = self.replay_flight_data("test_rdsclusterparamgroup_copy")
        client = session_factory().client("rds")

        name = "pgc-orig"
        copy_name = "pgc-copy"

        # Create the PG
        client.create_db_cluster_parameter_group(
            DBClusterParameterGroupName=name,
            DBParameterGroupFamily="aurora5.6",
            Description="test",
        )
        self.addCleanup(
            client.delete_db_cluster_parameter_group, DBClusterParameterGroupName=name
        )

        # Copy it via custodian
        p = self.load_policy(
            {
                "name": "rdspgc-copy",
                "resource": "rds-cluster-param-group",
                "filters": [{"DBClusterParameterGroupName": name}],
                "actions": [{"type": "copy", "name": copy_name}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Ensure it exists
        ret = client.describe_db_cluster_parameter_groups(
            DBClusterParameterGroupName=copy_name
        )
        self.assertEqual(len(ret["DBClusterParameterGroups"]), 1)
        self.addCleanup(
            client.delete_db_cluster_parameter_group,
            DBClusterParameterGroupName=copy_name,
        )

    @functional
    def test_rdsclusterparamgroup_modify(self):
        session_factory = self.replay_flight_data("test_rdsclusterparamgroup_modify")
        client = session_factory().client("rds")

        name = "pgc-test"

        # Create the PG
        client.create_db_cluster_parameter_group(
            DBClusterParameterGroupName=name,
            DBParameterGroupFamily="aurora5.6",
            Description="test",
        )
        self.addCleanup(
            client.delete_db_cluster_parameter_group, DBClusterParameterGroupName=name
        )

        # Modify it via custodian
        p = self.load_policy(
            {
                "name": "rdspgc-modify",
                "resource": "rds-cluster-param-group",
                "filters": [{"DBClusterParameterGroupName": name}],
                "actions": [
                    {
                        "type": "modify",
                        "params": [
                            {"name": "auto_increment_increment", "value": "1"},
                            {"name": "auto_increment_offset", "value": "2"},
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Ensure that params were set
        ret = client.describe_db_cluster_parameters(DBClusterParameterGroupName=name)
        count = 0
        for param in ret["Parameters"]:
            if param["ParameterName"] == "auto_increment_increment":
                self.assertEqual(param["ParameterValue"], "1")
                count += 1
            elif param["ParameterName"] == "auto_increment_offset":
                self.assertEqual(param["ParameterValue"], "2")
                count += 1
            if count == 2:
                break
        self.assertEqual(count, 2)
