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
import jmespath
from .core import Filter, ValueFilter
from c7n.utils import local_session, type_schema


class Subnet(ValueFilter):

    ResourceGroupIdsExpression = "VpcSecurityGroups"

    def get_subnet_ids(self, resource):
        pass

    def process(self, resources, event=None):
        pass


class SecurityGroup(ValueFilter):

    schema = type_schema(
        'security-group', rinherit=ValueFilter.schema,
        match_resource={'type': 'boolean'},
        operator={'enum': ['and', 'or']})

    # RDS DB Instance VpcSecurityGroups
    ResourceGroupIdsExpression = None

    def validate(self):
        if not self.ResourceGroupIdsExpression:
            raise ValueError(
                "Security Group filter missing group id expression")
        return self

    def get_group_ids(self, resources):
        all_groups = set(jmespath.search(
            "[].%s" % self.ResourceGroupIdsExpression, resources))
        return all_groups

    def get_groups(self, resources):
        from c7n.resources.vpc import SecurityGroup
        manager = SecurityGroup(self.manager.ctx, {})
        group_ids = self.get_group_ids(resources)
        return {g['GroupId']: g for g in manager.resources()
                if g['GroupId'] in group_ids}

    def process_resource(self, resource, groups):
        group_ids = jmespath.search(self.ResourceGroupIdsExpression, resource)
        model = self.manager.get_model()

        reducer = self.data.get('operator', 'or') == 'any' and any or all
        found = []

        value = None
        if self.data.get('match_resource'):
            pass

        for gid in group_ids:
            group = groups.get(gid, None)
            if group is None:
                self.log.warning(
                    "Resource %s:%s references non existant group: %s",
                    model.type, resource[model.id], gid)
                continue

            if self.match(group):
                found.append(gid)

        resource['c7n.security-groups'] = found
        return reducer(found)

    def process(self, resources, event=None):
        groups = self.get_groups(resources)
        return [r for r in resources if self.process_resource(r, groups)]


class DefaultVpcBase(Filter):

    vpcs = None
    default_vpc = None

    def match(self, vpc_id):
        if self.default_vpc is None:
            self.log.debug("querying default vpc %s" % vpc_id)
            client = local_session(self.manager.session_factory).client('ec2')
            vpcs = [v['VpcId'] for v
                    in client.describe_vpcs(VpcIds=[vpc_id])['Vpcs']
                    if v['IsDefault']]
            if not vpcs:
                self.default_vpc = ""
            else:
                self.default_vpc = vpcs.pop()
        return vpc_id == self.default_vpc and True or False
