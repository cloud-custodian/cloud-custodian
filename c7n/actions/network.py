# Copyright 2017-2018 Capital One Services, LLC
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
import six

from .core import Action


class ModifyVpcSecurityGroupsAction(Action):
    """Common actions for modifying security groups on a resource

    Can target either physical groups as a list of group ids or
    symbolic groups like 'matched', 'network-location' or 'all'. 'matched' uses
    the annotations of the 'security-group' interface filter. 'network-location' uses
    the annotations of the 'network-location' interface filter for `SecurityGroupMismatch`.

    Note an interface always gets at least one security group, so
    we mandate the specification of an isolation/quarantine group
    that can be specified if there would otherwise be no groups.

    type: modify-security-groups
        add: []
        remove: [] | matched | network-location
        isolation-group: sg-xyz
    """
    schema_alias = True
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['modify-security-groups']},
            'add': {'oneOf': [
                {'type': 'string', 'pattern': '^sg-*'},
                {'type': 'array', 'items': {
                    'pattern': '^sg-*',
                    'type': 'string'}}]},
            'remove': {'oneOf': [
                {'type': 'array', 'items': {
                    'type': 'string', 'pattern': '^sg-*'}},
                {'enum': [
                    'matched', 'network-location', 'all',
                    {'type': 'string', 'pattern': '^sg-*'}]}]},
            'isolation-group': {'oneOf': [
                {'type': 'string', 'pattern': '^sg-*'},
                {'type': 'array', 'items': {
                    'type': 'string', 'pattern': '^sg-*'}}]}},
        'anyOf': [
            {'required': ['isolation-group', 'remove', 'type']},
            {'required': ['add', 'remove', 'type']},
            {'required': ['add', 'type']}]
    }

    def get_groups(self, resources, metadata_key=None):
        """Parse policies to get lists of security groups to attach to each resource

        For each input resource, parse the various add/remove/isolation-
        group policies for 'modify-security-groups' to find the resulting
        set of VPC security groups to attach to that resource.

        The 'metadata_key' parameter can be used for two purposes at
        the moment; The first use is for resources' APIs that return a
        list of security group IDs but use a different metadata key
        than 'Groups' or 'SecurityGroups'.

        The second use is for when there are richer objects in the 'Groups' or
        'SecurityGroups' lists. The custodian actions need to act on lists of
        just security group IDs, so the metadata_key can be used to select IDs
        from the richer objects in the provided lists.

        Returns a list of lists containing the resulting VPC security groups
        that should end up on each resource passed in.

        :param resources: List of resources containing VPC Security Groups
        :param metadata_key: Metadata key for security groups list
        :return: List of lists of security groups per resource

        """
        # parse the add, remove, and isolation group params to return the
        # list of security groups that will end up on the resource
        # target_group_ids = self.data.get('groups', 'matched')

        add_target_group_ids = self.data.get('add', None)
        remove_target_group_ids = self.data.get('remove', None)
        isolation_group = self.data.get('isolation-group')
        add_groups = []
        remove_groups = []
        return_groups = []

        for idx, r in enumerate(resources):
            if r.get('Groups'):
                if metadata_key and isinstance(r['Groups'][0], dict):
                    rgroups = [g[metadata_key] for g in r['SecurityGroups']]
                else:
                    rgroups = [g['GroupId'] for g in r['Groups']]
            elif r.get('SecurityGroups'):
                # elb, ec2, elasticache, efs, dax vpc resource security groups
                if metadata_key and isinstance(r['SecurityGroups'][0], dict):
                    rgroups = [g[metadata_key] for g in r['SecurityGroups']]
                else:
                    rgroups = [g for g in r['SecurityGroups']]
            elif r.get('VpcSecurityGroups'):
                # rds resource security groups
                if metadata_key and isinstance(r['VpcSecurityGroups'][0], dict):
                    rgroups = [g[metadata_key] for g in r['VpcSecurityGroups']]
                else:
                    rgroups = [g for g in r['VpcSecurityGroups']]
            elif r.get('VPCOptions', {}).get('SecurityGroupIds', []):
                # elasticsearch resource security groups
                if metadata_key and isinstance(
                        r['VPCOptions']['SecurityGroupIds'][0], dict):
                    rgroups = [g[metadata_key] for g in r[
                        'VPCOptions']['SecurityGroupIds']]
                else:
                    rgroups = [g for g in r['VPCOptions']['SecurityGroupIds']]
            # use as substitution for 'Groups' or '[Vpc]SecurityGroups'
            # unsure if necessary - defer to coverage report
            elif metadata_key and r.get(metadata_key):
                rgroups = [g for g in r[metadata_key]]

            # Parse remove_groups
            if remove_target_group_ids == 'matched':
                remove_groups = r.get('c7n:matched-security-groups', ())
            elif remove_target_group_ids == 'network-location':
                for reason in r.get('c7n:NetworkLocation', ()):
                    if reason['reason'] == 'SecurityGroupMismatch':
                        remove_groups = list(reason['security-groups'])
            elif remove_target_group_ids == 'all':
                remove_groups = rgroups
            elif isinstance(remove_target_group_ids, list):
                remove_groups = remove_target_group_ids
            elif isinstance(remove_target_group_ids, six.string_types):
                remove_groups = [remove_target_group_ids]

            # Parse add_groups
            if isinstance(add_target_group_ids, list):
                add_groups = add_target_group_ids
            elif isinstance(add_target_group_ids, six.string_types):
                add_groups = [add_target_group_ids]

            # seems extraneous with list?
            # if not remove_groups and not add_groups:
            #     continue

            for g in remove_groups:
                if g in rgroups:
                    rgroups.remove(g)

            for g in add_groups:
                if g not in rgroups:
                    rgroups.append(g)

            if not rgroups:
                rgroups.append(isolation_group)

            return_groups.append(rgroups)

        return return_groups
