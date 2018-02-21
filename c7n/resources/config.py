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

from c7n.actions import BaseAction
from c7n.filters import ValueFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, chunks, type_schema


@resources.register('config-rule')
class ConfigRule(QueryResourceManager):

    class resource_type(object):
        service = "config"
        enum_spec = ("describe_config_rules", "ConfigRules", None)
        id = name = "ConfigRuleName"
        dimension = None
        filter_name = 'ConfigRuleNames'
        filter_type = 'list'


@ConfigRule.filter_registry.register('status')
class RuleStatus(ValueFilter):

    schema = type_schema('status', rinherit=ValueFilter.schema)
    permissions = ('config:DescribeConfigRuleEvaluationStatus',)
    annotate = False

    def process(self, resources, event=None):
        status_map = {}
        client = local_session(self.manager.session_factory).client('config')

        for rule_set in chunks(resources, 100):
            for status in client.describe_config_rule_evaluation_status(
                ConfigRuleNames=[r['ConfigRuleName'] for r in rule_set]).get(
                    'ConfigRulesEvaluationStatus', []):
                status_map[status['ConfigRuleName']] = status

        results = []
        for r in resources:
            r['c7n:status'] = status_map.get(r['ConfigRuleName'])
            if self.match(r['c7n:status']):
                results.append(r)
        return results


@ConfigRule.action_registry.register('delete')
class DeleteRule(BaseAction):

    schema = type_schema('delete')
    permissions = ('config:DeleteConfigRule',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('config')
        for r in resources:
            client.delete_config_rule(
                ConfigRuleName=r['ConfigRuleName'])
