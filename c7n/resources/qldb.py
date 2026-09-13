# Copyright 2020 Cloud Custodian Authors
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from c7n.actions import BaseAction as Action
from c7n.deprecated import DeprecatedResource
from c7n.query import QueryResourceManager, TypeInfo
from c7n.manager import resources
from c7n.utils import type_schema


@resources.register('qldb')
@DeprecatedResource(
    "QLDB is no longer an available AWS service",
    removed_after="2027-07-23", force_empty=True)
class QLDB(QueryResourceManager):

    class resource_type(TypeInfo):
        arn_type = 'ledger'

        id = name = 'Name'
        date = 'CreationDateTime'
        universal_taggable = object()
        cfn_type = config_type = 'AWS::QLDB::Ledger'
        permissions_augment = ("qldb:ListTagsForResource",)


@QLDB.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('qldb:DeleteLedger', 'qldb:UpdateLedger')

    def process(self, resources):
        return
