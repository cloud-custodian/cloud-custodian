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

import logging

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import IpRangeHelper
from c7n_azure.utils import ThreadHelper
from netaddr import IPRange

from c7n.filters import Filter, FilterValidationError
from c7n.filters.core import type_schema

log = logging.getLogger('custodian.azure.sqlserver')


@resources.register('sqlserver')
class SqlServer(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.sql'
        client = 'SqlManagementClient'
        enum_spec = ('servers', 'list', None)


@SqlServer.filter_registry.register('firewall-rules')
class SqlServerFirewallRulesFilter(Filter):
    """Filters SQL servers by the firewall rules

    :example:

    .. code-block:: yaml

            policies:
                - name: servers-with-firewall
                  resource: azure.sqlserver
                  filters:
                      - type: firewall-rules
                        include:
                            - '131.107.160.2-131.107.160.3'
                            - 10.20.20.0/24
    """

    schema = type_schema(
        'firewall-rules',
        **{
            'include': {'type': 'array', 'items': {'type': 'string'}},
            'equal': {'type': 'array', 'items': {'type': 'string'}}
        })

    def __init__(self, data, manager=None):
        super(SqlServerFirewallRulesFilter, self).__init__(data, manager)
        self.policy_include = None
        self.policy_equal = None
        self.client = None

    def validate(self):
        self.policy_include = IpRangeHelper.parse_ip_ranges(self.data, 'include')
        self.policy_equal = IpRangeHelper.parse_ip_ranges(self.data, 'equal')

        has_include = self.policy_include is not None
        has_equal = self.policy_equal is not None

        if has_include and has_equal:
            raise FilterValidationError('Cannot have both include and equal.')

        if not has_include and not has_equal:
            raise FilterValidationError('Must have either include or equal.')

        return True

    def process(self, resources, event=None):
        self.client = self.manager.get_client()

        result, _ = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._check_resources,
            executor_factory=self.executor_factory,
            log=log
        )

        return result

    def _check_resources(self, resources, event):
        return [r for r in resources if self._check_resource(r)]

    def _check_resource(self, resource):
        try:
            query = self.client.firewall_rules.list_by_server(
                resource['resourceGroup'],
                resource['name'])

            resource_rules = set([IPRange(r.start_ip_address, r.end_ip_address) for r in query])
        except Exception as error:
            log.warning(error)
            return False

        ok = self._check_rules(resource_rules)

        return ok

    def _check_rules(self, resource_rules):
        if self.policy_equal is not None:
            return self.policy_equal == resource_rules
        elif self.policy_include is not None:
            return self.policy_include.issubset(resource_rules)
        else:  # validated earlier, can never happen
            raise FilterValidationError("Internal error.")
