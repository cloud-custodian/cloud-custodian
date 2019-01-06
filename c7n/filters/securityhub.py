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

from c7n.utils import local_session, chunks, type_schema
from .core import Filter
from c7n.manager import resources


class SecurityHubFindingFilter(Filter):
    """Check if there are Security Hub Findings related to the resources
    """
    schema = type_schema(
        'finding'
        )
    permissions = ('securityhub:GetFindings',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            'securityhub', region_name='us-east-1')

        if self.manager.data['resource'] in {'app-elb'}:
            id_attr = self.manager.get_model().name
        else:
            id_attr = self.manager.get_model().id
        resource_map = {r[id_attr]: r for r in resources}
        found = set()

        for resource_set in chunks(resource_map.keys(), 100):
            for resource in resource_set:
                # TODO: Support parameterized filters rather not just finding exists
                self.log.debug("resource level arn=%s", self.manager.generate_arn(resource))
                f = {
                    "ResourceId": [
                        {
                            "Value": self.manager.generate_arn(resource),
                            "Comparison": "EQUALS",
                        }
                    ]
                }
                self.log.debug("filter=%s", f)
                findings = client.get_findings(Filters=f).get("Findings")

                if len(findings) > 0:
                    found.add(resource)

        return [resource_map[resource_id] for resource_id in found]

    @classmethod
    def register_resources(klass, registry, resource_class):
        """ meta model subscriber on resource registration.

        SecurityHub Findings Filter
        """
        for rtype, resource_manager in registry.items():
            if 'post-finding' in resource_manager.action_registry:
                continue
            resource_class.filter_registry.register('finding', klass)


resources.subscribe(resources.EVENT_REGISTER, SecurityHubFindingFilter.register_resources)
