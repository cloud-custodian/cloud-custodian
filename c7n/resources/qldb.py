# Copyright 2020 Cloud Custodian Authors
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from c7n.actions import BaseAction as Action
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.manager import resources
from c7n.utils import local_session, type_schema



class DescribeRemoved(DescribeSource):
    def resources(self, query):
        return []

    def get_resources(self, resource_ids):
        return []


@resources.register('qldb')
class QLDB(QueryResourceManager):

    class resource_type(TypeInfo):
        arn_type = 'ledger'

        id = name = 'Name'
        date = 'CreationDateTime'
        universal_taggable = object()
        cfn_type = config_type = 'AWS::QLDB::Ledger'
        permissions_augment = ("qldb:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeRemoved,
        'config': ConfigSource
    }

    def get_permissions(self):
        return []


@QLDB.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('qldb:DeleteLedger', 'qldb:UpdateLedger')

    def process(self, resources):
        return
