# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
                 value_type: age
                 value: 30
                 op: less-than
              rules:
               - custodian-ec2-encryption-required
               - custodian-ec2-tags-required

    Also note, custodian has direct support for deploying policies as config
    rules see https://cloudcustodian.io/docs/policy/lambda.html#config-rules
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
    schema_alias = True
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
                    if rident['ResourceType'] not in (
                            resource_model.config_type,
                            resource_model.cfn_type):
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

        # Avoid static/import time dep on boto in filters package
        from c7n.resources.aws import Arn
        results = []
        for arn, r in zip(self.manager.get_arns(resources), resources):
            # many aws provided rules are inconsistent in their
            # treatment of resource ids, some use arns, some use names
            # as identifiers for the same resource type. security
            # hub in particular is bad at consistency.
            rid = None
            if arn in resource_map:
                rid = arn
            elif r[resource_model.id] in resource_map:
                rid = r[resource_model.id]
            if arn == r[resource_model.id] and not rid:
                rid = Arn.parse(arn).resource
                if rid not in resource_map:
                    rid = None
            if rid is None:
                continue
            r[self.annotation_key] = resource_map[rid]
            results.append(r)
        return results

    @classmethod
    def register_resources(klass, registry, resource_class):
        """model resource subscriber on resource registration.

        Watch for new resource types being registered if they are
        supported by aws config, automatically, register the
        config-compliance filter.
        """
        if (resource_class.resource_type.cfn_type is None and
                resource_class.resource_type.config_type is None):
            return
        resource_class.filter_registry.register('config-compliance', klass)


resources.subscribe(ConfigCompliance.register_resources)
