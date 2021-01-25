# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.query import QueryResourceManager, TypeInfo
from c7n.manager import resources


@resources.register('iot')
class IoT(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'iot'
        enum_spec = ('list_things', 'things', None)
        name = "thingName"
        id = "thingName"
        arn = "thingArn"
        default_report_fields = (
            'thingName',
            'thingTypeName'
        )
        cfn_type = 'AWS::IoT::Thing'
