# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('support-case')
class SupportCase(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'support'
        enum_spec = ('describe_cases', 'cases', None)
        filter_name = 'caseIdList'
        filter_type = 'list'
        id = 'caseId'
        name = 'displayId'
        date = 'timeCreated'
        arn = False
