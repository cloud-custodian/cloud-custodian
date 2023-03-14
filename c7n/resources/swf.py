# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.tags import universal_augment


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
