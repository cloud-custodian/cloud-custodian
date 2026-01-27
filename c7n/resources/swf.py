# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import ValueFilter
from c7n.manager import resources
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema


class DescribeSimpleWorkflow(DescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('swf-domain')
class SimpleWorkflowDomain(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'swf'
        arn_type = ''
        enum_spec = ('list_domains', 'domainInfos', {'registrationStatus': 'REGISTERED'})
        id = name = 'name'
        arn = 'arn'
        universal_taggable = object()
        permission_augment = ('swf:ListTagsForResource',)

    source_mapping = {
        'describe': DescribeSimpleWorkflow,
        'config': ConfigSource
    }


@SimpleWorkflowDomain.filter_registry.register('configuration')
class SWFConfigurationFilter(ValueFilter):

    annotation_key = "c7n:configuration"
    permissions = ("swf:DescribeDomain",)
    schema = type_schema('configuration', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('swf')
        results = []
        for r in resources:
            if self.annotation_key not in r:
                config = self.manager.retry(client.describe_domain, name=r["name"])["configuration"]
                config["workflowExecutionRetentionPeriodInDays"] = int(
                    config["workflowExecutionRetentionPeriodInDays"])
                r[self.annotation_key] = config

            if self.match(r[self.annotation_key]):
                results.append(r)
        return results
