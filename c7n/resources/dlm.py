# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('dlm-policy')
class DLMPolicy(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'dlm'
        id = name = 'PolicyId'
        enum_spec = (
            'get_lifecycle_policies', 'Policies', None)
        detail_spec = ('get_lifecycle_policy', 'PolicyId', 'PolicyId', 'Policy')
        filter_name = 'PolicyIds'
        filter_type = 'list'
        arn = False
        cfn_type = 'AWS::DLM::LifecyclePolicy'
