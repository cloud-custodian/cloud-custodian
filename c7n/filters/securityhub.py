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
import json

from c7n.utils import local_session, type_schema
from .core import Filter
from c7n.manager import resources
from c7n.exceptions import PolicyValidationError
from c7n.resources import aws


class SecurityHubFindingFilter(Filter):
    """Check if there are Security Hub Findings related to the resources
    """
    schema = type_schema(
        'finding',
        filter_json={'type': 'string'}
    )
    permissions = ('securityhub:GetFindings',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            'securityhub', region_name='us-east-1')
        annotation_key = 'c7n:finding-filter'
        found = []
        f = self.get_filter_parameters()

        for resource in resources:
            f['ResourceId'] = [
                {
                    "Value": self.manager.get_arns([resource])[0],
                    "Comparison": "EQUALS",
                }
            ]

            self.log.debug("filter=%s", f)
            findings = client.get_findings(Filters=f).get("Findings")

            if len(findings) > 0:
                resource[annotation_key] = json.dumps(f)
                found.append(resource)


        return found

    def get_filter_parameters(self):
        f = {}
        if self.data.get('filter_json'):
            f = json.loads(self.data.get('filter_json'))
        return f

    def validate(self):
        if self.data.get('filter_json'):
            if aws.shape_validate(
                    json.loads(self.data.get('filter_json')),
                    'AwsSecurityFindingFilters', 'securityhub'):
                raise PolicyValidationError(
                    "finding requires json formated to the spec at\
                    https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/\
                    securityhub.html#SecurityHub.Client.get_findings")

        return self

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
