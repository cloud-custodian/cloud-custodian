# Copyright 2018 Capital One Services, LLC
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

from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session


@resources.register('neptune-cluster')
class NeptuneCluster(QueryResourceManager):

    class resource_type(object):
        service = 'neptune'
        enum_spec = ('describe_db_clusters', 'DBClusters', None)
        id = 'DBClusterIdentifier'
        name = 'DatabaseName'
        date = 'ClusterCreateTime'
        dimension = 'DBClusterIdentifier'
        filter_name = 'DBClusterIdentifier'


@NeptuneCluster.filter_registry.register('security-group')
class ClusterSecurityGroup(SecurityGroupFilter):

    RelatedIdsExpression = "VpcSecurityGroups[].VpcSecurityGroupId"


@NeptuneCluster.filter_registry.register('subnet')
class ClusterSubnet(SubnetFilter):

    RelatedIdsExpression = ""

    def get_related_ids(self, resources):
        group_ids = set()
        for r in resources:
            group_ids.update(self.groups[r['DBSubnetGroupName']])
        return group_ids

    def process(self, resources, event=None):
        client = local_session(self.manager.local_session).client('neptune')
        self.groups = {
            g['DBSubnetGroupName']: [s['SubnetIdentifier'] for s in g['Subnets']]
            for g in client.describe_db_subnet_groups().get('DBSubnetGroups')}
        return super(ClusterSubnet, self).process(resources, event)
