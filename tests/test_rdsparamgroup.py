# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from .common import BaseTest, functional


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

    def test_rdsparamgroup_unused(self):
        session_factory = self.replay_flight_data("test_rdsparamgroup_unused")
        policy = self.load_policy(
            {
                "name": "rds-param-group-unused",
                "resource": "rds-param-group",
                "filters": [{"type": "unused"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        names = {r['DBParameterGroupName'] for r in resources}
        self.assertIn("default.mysql8.0", names)
        self.assertIn("custom-pg-orphan", names)
        self.assertNotIn("custom-pg-used", names)

    def test_rdsparamgroup_param_value_filter(self):
        session_factory = self.replay_flight_data('test_rdsparamgroup_param_value_filter')
        policy = self.load_policy(
            {
                "name": "rds-paramter-group-value-filter-test",
                "resource": "rds-param-group",
                "filters": [
                    {
                        "type": "db-parameter",
                        "key": "tls_version",
                        "op": "eq",
                        "value": "TLSv1.2"
                    }
                ]
            },
            session_factory=session_factory,
        )

        resources = policy.resource_manager.resources()
        self.assertEqual(len(resources), 1)


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

    def test_rdsclusterparamgroup_unused(self):
        session_factory = self.replay_flight_data("test_rdsclusterparamgroup_unused")
        policy = self.load_policy(
            {
                "name": "rds-cluster-param-group-unused",
                "resource": "rds-cluster-param-group",
                "filters": [{"type": "unused"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        names = {r['DBClusterParameterGroupName'] for r in resources}
        self.assertIn("default.aurora-mysql8.0", names)
        self.assertIn("custom-cluster-pg-orphan", names)
        self.assertNotIn("custom-cluster-pg-used", names)

    def test_rdsclusterparamgroup_param_value_filter(self):
        session_factory = self.replay_flight_data('test_rdsclusterparamgroup_param_value_filter')
        policy = self.load_policy(
            {
                "name": "rdscluster-paramter-group-value-filter-test",
                "resource": "rds-cluster-param-group",
                "filters": [
                    {
                        "type": "db-parameter",
                        "key": "tls_version",
                        "op": "eq",
                        "value": "TLSv1.2"
                    }
                ]
            },
            session_factory=session_factory,
        )

        resources = policy.resource_manager.resources()
        self.assertEqual(len(resources), 1)


class ParamGroupCurrentParamsTest(BaseTest):

    def stubbed_client(self, method, name_key):
        client = boto3.Session(region_name='us-east-1').client(
            'rds', aws_access_key_id='x', aws_secret_access_key='x')
        stubber = Stubber(client)
        param = {'ParameterValue': '1', 'ApplyMethod': 'immediate'}
        stubber.add_response(
            method, {'Parameters': [dict(param, ParameterName='autocommit')], 'Marker': 'm1'},
            {name_key: 'pg'})
        stubber.add_response(
            method, {'Parameters': [dict(param, ParameterName='max_connections')]},
            {name_key: 'pg', 'Marker': 'm1'})
        stubber.activate()
        self.addCleanup(stubber.deactivate)
        return client, stubber

    def check(self, resource, method, name_key):
        p = self.load_policy({
            'name': 'pg-modify', 'resource': resource,
            'actions': [{'type': 'modify', 'params': [{'name': 'autocommit', 'value': '0'}]}]})
        client, stubber = self.stubbed_client(method, name_key)
        params = p.resource_manager.actions[0].get_current_params(client, 'pg')
        self.assertEqual(sorted(params), ['autocommit', 'max_connections'])
        stubber.assert_no_pending_responses()

    def test_db_parameter_group_params_paginated(self):
        self.check('rds-param-group', 'describe_db_parameters', 'DBParameterGroupName')

    def test_cluster_parameter_group_params_paginated(self):
        self.check(
            'rds-cluster-param-group', 'describe_db_cluster_parameters',
            'DBClusterParameterGroupName')
