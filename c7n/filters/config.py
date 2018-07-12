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

from c7n.filters import ValueFilter
from c7n.manager import resources
from c7n.utils import local_session, type_schema

from .core import Filter


class ConfigCompliance(Filter):
    """Filter resources by their compliance with one or more AWS config rules.

    An example of using the filter to find all ec2 instances that have
    been registered as non compliant in the last 30 days against two
    custom AWS Config rules.

    :example:

    .. code-block:: yaml

       policies:
         - name: non-compliant-ec2
           resource: ec2
           filters:
            - type: config-compliance
              eval_filters:
               - type: value
                 key: ResultRecordedTime
                 type: age
                 value: 30
                 op: less-thanx
              rules:
               - custodian-ec2-encryption-required
               - custodian-ec2-tags-required

    Also note, custodian has direct support for deploying policies as config
    rules see https://bit.ly/2mblVpq
    """
    permissions = ('config:DescribeComplianceByConfigRule',)
    schema = type_schema(
        'config-compliance',
        required=('rules',),
        op={'enum': ['or', 'and']},
        eval_filters={'type': 'array', 'items': {
            'oneOf': [
                {'$ref': '#/definitions/filters/valuekv'},
                {'$ref': '#/definitions/filters/value'}]}},
        states={'type': 'array', 'items': {'enum': [
            'COMPLIANT', 'NON_COMPLIANT',
            'NOT_APPLICABLE', 'INSUFFICIENT_DATA']}},
        rules={'type': 'array', 'items': {'type': 'string'}})

    annotation_key = 'c7n:config-compliance'

    def get_resource_map(self, filters, resource_model, resources):
        rule_ids = self.data.get('rules')
        states = self.data.get('states', ['NON_COMPLIANT'])
        op = self.data.get('op', 'or') == 'or' and any or all

        client = local_session(self.manager.session_factory).client('config')
        resource_map = {}

        for rid in rule_ids:
            pager = client.get_paginator('get_compliance_details_by_config_rule')
            for page in pager.paginate(
                    ConfigRuleName=rid, ComplianceTypes=states):
                evaluations = page.get('EvaluationResults', ())

                for e in evaluations:
                    rident = e['EvaluationResultIdentifier'][
                        'EvaluationResultQualifier']
                    # for multi resource type rules, only look at
                    # results for the resource type currently being
                    # processed.
                    if rident['ResourceType'] != resource_model.config_type:
                        continue

                    if not filters:
                        resource_map.setdefault(
                            rident['ResourceId'], []).append(e)
                        continue

                    if op([f.match(e) for f in filters]):
                        resource_map.setdefault(
                            rident['ResourceId'], []).append(e)

        return resource_map

    def process(self, resources, event=None):
        filters = []
        for f in self.data.get('eval_filters', ()):
            vf = ValueFilter(f)
            vf.annotate = False
            filters.append(vf)

        resource_model = self.manager.get_model()
        resource_map = self.get_resource_map(filters, resource_model, resources)

        results = []
        for r in resources:
            if r[resource_model.id] not in resource_map:
                continue
            r[self.annotation_key] = resource_map[r[resource_model.id]]
            results.append(r)
        return results

    @classmethod
    def register_resources(klass, registry, resource_class):
        """model resource subscriber on resource registration.

        Watch for new resource types being registered if they support aws config,
        automatically, register the config-compliance filter.
        """

        config_type = getattr(resource_class.resource_type, 'config_type', None)
        if config_type is None:
            return
        resource_class.filter_registry.register('config-compliance', klass)


resources.subscribe(resources.EVENT_REGISTER, ConfigCompliance.register_resources)
