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
from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest, functional
from botocore.exceptions import ClientError


class RDSParamGroupTest(BaseTest):

    @functional
    def test_rdsparamgroup_delete(self):
        session_factory = self.replay_flight_data('test_rdsparamgroup_delete')
        client = session_factory().client('rds')

        name = 'pg-test'

        # Create the PG
        client.create_db_parameter_group(
            DBParameterGroupName=name,
            DBParameterGroupFamily='mysql5.5',
            Description='test'
        )

        # Ensure it exists
        ret = client.describe_db_parameter_groups(DBParameterGroupName=name)
        self.assertEqual(len(ret['DBParameterGroups']), 1)

        # Delete it via custodian
        p = self.load_policy({
            'name': 'rdspg-delete',
            'resource': 'rds-param-group',
            'filters': [{'DBParameterGroupName': name}],
            'actions': [{'type': 'delete'}],
            }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify it is gone
        try:
            client.describe_db_parameter_groups(DBParameterGroupName=name)
        except ClientError:
            pass
        else:
            self.fail('parameter group {} still exists'.format(name))


class RDSClusterParamGroupTest(BaseTest):

    @functional
    def test_rdsclusterparamgroup_delete(self):
        session_factory = self.replay_flight_data('test_rdsclusterparamgroup_delete')
        client = session_factory().client('rds')

        name = 'pg-cluster-test'

        # Create the PG
        client.create_db_cluster_parameter_group(
            DBClusterParameterGroupName=name,
            DBParameterGroupFamily='aurora5.6',
            Description='test'
        )

        # Ensure it exists
        ret = client.describe_db_cluster_parameter_groups(DBClusterParameterGroupName=name)
        self.assertEqual(len(ret['DBClusterParameterGroups']), 1)

        # Delete it via custodian
        p = self.load_policy({
            'name': 'rdspgc-delete',
            'resource': 'rds-cluster-param-group',
            'filters': [{'DBClusterParameterGroupName': name}],
            'actions': [{'type': 'delete'}],
            }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify it is gone
        try:
            client.describe_db_cluster_parameter_groups(DBClusterParameterGroupName=name)
        except ClientError:
            pass
        else:
            self.fail('parameter group cluster {} still exists'.format(name))

