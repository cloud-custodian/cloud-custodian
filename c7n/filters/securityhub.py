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

from c7n.utils import local_session, type_schema
from .core import Filter
from c7n.manager import resources
from c7n.resources import aws


class SecurityHubFindingFilter(Filter):
    """Check if there are Security Hub Findings related to the resources
    """
    schema = type_schema(
        'finding',
        # Many folks do an aggregator region, allow them to use that
        # for filtering.
        region={'type': 'string'},
        query={'type': 'object'})

    permissions = ('securityhub:GetFindings',)
    annotation_key = 'c7n:finding-filter'
    query_shape = 'AwsSecurityFindingFilters'

    def validate(self):
        query = self.data.get('query')
        if query:
            aws.shape_validate(query, self.query_shape, 'securityhub')

    def process(self, resources, event=None):
        client = local_session(
            self.manager.session_factory).client(
                'securityhub', region_name=self.data.get('region'))
        found = []
        params = dict(self.data.get('query', {}))

        for r_arn, resource in zip(self.manager.get_arns(resources), resources):
            params['ResourceId'] = [{"Value": r_arn, "Comparison": "EQUALS"}]
            findings = client.get_findings(Filters=params).get("Findings")
            if len(findings) > 0:
                resource[self.annotation_key] = findings
                found.append(resource)
        return found

    @classmethod
    def register_resources(klass, registry, resource_class):
        """ meta model subscriber on resource registration.

        SecurityHub Findings Filter
        """
        for rtype, resource_manager in registry.items():
            if not resource_manager.has_arn():
                continue
            if 'post-finding' in resource_manager.action_registry:
                continue
            resource_class.filter_registry.register('finding', klass)


resources.subscribe(resources.EVENT_REGISTER, SecurityHubFindingFilter.register_resources)
